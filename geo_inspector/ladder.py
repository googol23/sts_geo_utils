"""Extract nominal sensor boxes for a ladder or a parent geometry node."""

import argparse
import csv
import json
import math
import re
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, replace
from itertools import product
from pathlib import Path

from .extraction import extract_geometry
from .sts import NUMERIC_FIELDS, ROTATION_FIELDS

# Match placed legacy/v26a ladders, as well as volume-rooted ladder exports.
_LADDER_NAME = re.compile(r"(?:LadderType\d+|Ladder_LadderType\d+)(?:_\d+)?")
_HALF_UNIT_NAME = re.compile(r"Unit\d+[RL](?:_\d+)?")


@dataclass(frozen=True)
class BoundingBox:
    """Axis-aligned bounds in the selected coordinate frame, in cm."""

    minimum: tuple[float, float, float]
    maximum: tuple[float, float, float]

    @classmethod
    def from_points(cls, points):
        points = tuple(points)
        return cls(
            tuple(min(point[i] for point in points) for i in range(3)),
            tuple(max(point[i] for point in points) for i in range(3)),
        )

    def to_dict(self):
        return {"min": self.minimum, "max": self.maximum}


@dataclass(frozen=True)
class NodeFrame:
    """Node-local reference frame: ``global = translation + rotation @ point``."""

    node_path: str
    translation: tuple[float, float, float]
    rotation: tuple[tuple[float, float, float], ...]

    def to_dict(self):
        return {"translation": self.translation, "rotation": self.rotation}


@dataclass(frozen=True)
class SensorGeometry:
    """A sensor box; ``frame_point = center + rotation @ local_displacement``.

    Dimensions are full lengths along the sensor's local axes, not global
    axis-aligned extents. The center includes the ROOT shape's box origin.
    All lengths are in cm; rotation is a row-major 3x3 matrix.
    """

    node_path: str
    center: tuple[float, float, float]
    dimensions: tuple[float, float, float]
    rotation: tuple[tuple[float, float, float], ...]

    @property
    def corners(self):
        """Eight reference-frame corners, ordered by local signs (-,-,-) to (+,+,+)."""
        return tuple(
            tuple(
                self.center[i]
                + sum(
                    self.rotation[i][j] * signs[j] * self.dimensions[j] / 2
                    for j in range(3)
                )
                for i in range(3)
            )
            for signs in product((-1, 1), repeat=3)
        )

    @property
    def bounds(self):
        return BoundingBox.from_points(self.corners)

    def to_dict(self):
        return {
            "node_path": self.node_path,
            "center": self.center,
            "dimensions": self.dimensions,
            "rotation": self.rotation,
            "corners": self.corners,
            "bounds": self.bounds.to_dict(),
        }


@dataclass(frozen=True)
class LadderGeometry:
    """Sensor placements in one ladder; bounds exclude non-sensor material."""

    node_path: str
    sensors: tuple[SensorGeometry, ...]
    reference_frame: NodeFrame | None = None

    @property
    def bounds(self):
        return BoundingBox.from_points(
            corner for sensor in self.sensors for corner in sensor.corners
        )

    def to_dict(self):
        payload = {
            "schema_version": 2 if self.reference_frame else 1,
            "units": "cm",
            "coordinate_frame": "node" if self.reference_frame else "global",
            "node_path": self.node_path,
            "sensor_count": len(self.sensors),
            "bounds": self.bounds.to_dict(),
            "sensors": [sensor.to_dict() for sensor in self.sensors],
        }
        if self.reference_frame is not None:
            payload["reference_node"] = self.reference_frame.node_path
            payload["reference_to_global"] = self.reference_frame.to_dict()
        return payload


def _read_rows(sensor_csv, *, require_dimensions=True):
    with Path(sensor_csv).open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        required = {"node_path", "x", "y", "z", *ROTATION_FIELDS}
        if require_dimensions:
            required.update(NUMERIC_FIELDS)
        missing = required.difference(reader.fieldnames or ())
        if missing:
            raise ValueError(
                f"Sensor CSV is missing columns: {', '.join(sorted(missing))}"
            )
        rows = list(reader)
    for row in rows:
        path = row["node_path"]
        if (
            not path
            or not path.startswith("/")
            or any(not part for part in path[1:].split("/"))
        ):
            raise ValueError(f"Invalid absolute geometry node path: {path!r}")
    return rows


def _ladder_paths(rows):
    paths = set()
    for row in rows:
        names = row["node_path"].strip("/").split("/")
        for index, name in enumerate(names):
            if _LADDER_NAME.fullmatch(name):
                paths.add("/" + "/".join(names[: index + 1]))
    return tuple(sorted(paths))


def available_ladders(sensor_csv):
    """Return full ladder paths with sensors in an ``extract_geometry`` CSV."""
    return _ladder_paths(_read_rows(sensor_csv))


def load_ladder_geometry(sensor_csv, ladder, *, frame="auto", node_transforms=None):
    """Read a ladder from an existing full-size/orientation extraction CSV.

    ``ladder`` is an exact absolute node path or an unambiguous node name.
    Layout IDs and manufacturing names are deliberately not inferred. ``auto``
    uses global coordinates for a ladder; ``node`` uses its own local frame and
    requires the optional node-transform CSV. ``global`` always keeps global poses.
    """
    rows = _read_rows(sensor_csv)
    node_path = _resolve_node(_ladder_paths(rows), ladder, "Ladder")
    reference = _reference_frame(node_path, frame, node_transforms)
    return _in_reference_frame(_load_ladder(rows, node_path), reference)


def _resolve_node(paths, node, label="Node"):
    selector = str(node).rstrip("/") or ("/" if str(node).startswith("/") else "")
    matches = [
        path
        for path in paths
        if selector
        and (
            path == selector
            if selector.startswith("/")
            else path.rsplit("/", 1)[-1] == selector
        )
    ]
    if not matches:
        raise ValueError(
            f"{label} not found: {node!r}; use --list to see available ladder paths"
        )
    if len(matches) != 1:
        raise ValueError(
            f"Ambiguous {label.lower()} {node!r}; use a full path: {', '.join(matches)}"
        )
    return matches[0]


def _select_ladder_paths(rows, node):
    ladders = _ladder_paths(rows)
    ancestors = set()
    for path in ladders:
        names = path.strip("/").split("/")
        ancestors.update("/" + "/".join(names[:i]) for i in range(len(names) + 1))
    selected = _resolve_node(sorted(ancestors), node)
    prefix = selected.rstrip("/") + "/"
    return selected, tuple(
        path for path in ladders if path == selected or path.startswith(prefix)
    )


def load_ladder_geometries(sensor_csv, node, *, frame="auto", node_transforms=None):
    """Read all sensor-bearing ladders at or below a full path or unique node name.

    A parent with just one ladder still returns a tuple. Nodes without any
    sensor-bearing ladder descendants are not present in the extraction CSV.
    ``frame='auto'`` uses the selected half-unit's local frame for UnitNNL/R nodes
    and global coordinates otherwise. Node-frame loading requires ``node_transforms``.
    """
    rows = _read_rows(sensor_csv)
    selected, paths = _select_ladder_paths(rows, node)
    reference = _reference_frame(selected, frame, node_transforms)
    return tuple(
        _in_reference_frame(_load_ladder(rows, path), reference) for path in paths
    )


def _load_ladder(rows, node_path):
    sensors = []
    seen = set()
    for row in rows:
        path = row["node_path"]
        if not path.startswith(node_path + "/"):
            continue
        if path in seen:
            raise ValueError(f"Duplicate sensor node path: {path}")
        seen.add(path)
        try:
            values = tuple(
                float(row[field]) for field in (*NUMERIC_FIELDS, *ROTATION_FIELDS)
            )
        except (TypeError, ValueError) as error:
            raise ValueError(f"Invalid sensor geometry at {path}") from error
        if not all(math.isfinite(value) for value in values) or any(
            value <= 0 for value in values[3:6]
        ):
            raise ValueError(
                f"Non-finite geometry or non-positive sensor dimensions at {path}"
            )
        rotation = tuple(
            (values[6 + 3 * i], values[7 + 3 * i], values[8 + 3 * i]) for i in range(3)
        )
        _validate_rotation(rotation, path)
        center = (values[0], values[1], values[2])
        dimensions = (values[3], values[4], values[5])
        sensors.append(SensorGeometry(path, center, dimensions, rotation))
    if not sensors:
        raise ValueError(f"No sensors found below ladder: {node_path}")
    return LadderGeometry(
        node_path, tuple(sorted(sensors, key=lambda sensor: sensor.node_path))
    )


def _triple(values) -> tuple[float, float, float]:
    return values[0], values[1], values[2]


def _validate_rotation(rotation, path):
    if any(
        not math.isclose(
            sum(rotation[k][i] * rotation[k][j] for k in range(3)),
            float(i == j),
            abs_tol=1e-8,
        )
        for i in range(3)
        for j in range(3)
    ):
        raise ValueError(f"Orientation is not orthonormal at {path}")


def _reference_frame(selected, frame, node_transforms):
    if frame not in ("auto", "global", "node"):
        raise ValueError(
            f"Unsupported coordinate frame: {frame!r}; use auto, global or node"
        )
    use_node = frame == "node" or (
        frame == "auto"
        and _HALF_UNIT_NAME.fullmatch(selected.rsplit("/", 1)[-1]) is not None
    )
    if not use_node:
        return None
    if node_transforms is None:
        raise ValueError(
            "Node-frame coordinates require node transforms from the ROOT geometry; "
            "pass node_transforms or explicitly select frame='global'"
        )
    matches = [
        row
        for row in _read_rows(node_transforms, require_dimensions=False)
        if row["node_path"] == selected
    ]
    if len(matches) != 1:
        raise ValueError(
            f"Expected exactly one transform for reference node: {selected}"
        )
    row = matches[0]
    try:
        values = tuple(float(row[field]) for field in ("x", "y", "z", *ROTATION_FIELDS))
    except (ValueError, TypeError) as error:
        raise ValueError(f"Invalid reference node transform: {selected}") from error
    if not all(math.isfinite(value) for value in values):
        raise ValueError(f"Non-finite reference node transform: {selected}")
    rotation = tuple(_triple(values[3 + 3 * i : 6 + 3 * i]) for i in range(3))
    _validate_rotation(rotation, selected)
    return NodeFrame(selected, _triple(values), rotation)


def _in_reference_frame(ladder, reference):
    if reference is None:
        return ladder
    # T_sensor_to_ref = inverse(T_ref_to_global) * T_sensor_to_global.
    # Orthogonal TGeo rotations are inverted by transposition, not by negation.
    inverse = tuple(
        (reference.rotation[0][i], reference.rotation[1][i], reference.rotation[2][i])
        for i in range(3)
    )
    sensors = []
    for sensor in ladder.sensors:
        displacement = tuple(
            sensor.center[i] - reference.translation[i] for i in range(3)
        )
        center = tuple(
            sum(inverse[i][j] * displacement[j] for j in range(3)) for i in range(3)
        )
        rotation = tuple(
            _triple(
                tuple(
                    sum(inverse[i][k] * sensor.rotation[k][j] for k in range(3))
                    for j in range(3)
                )
            )
            for i in range(3)
        )
        sensors.append(replace(sensor, center=_triple(center), rotation=rotation))
    return replace(ladder, sensors=tuple(sensors), reference_frame=reference)


@contextmanager
def _extracted_csv(geometry, root):
    with tempfile.TemporaryDirectory(prefix="geo-inspector-ladder-") as directory:
        sensor_csv = Path(directory) / "sensors.csv"
        node_csv = Path(directory) / "nodes.csv"
        # Keep CLI stdout machine-readable even when ROOT prints startup logs.
        extract_geometry(
            geometry, sensor_csv, root, stdout=sys.stderr, node_transforms=node_csv
        )
        yield sensor_csv, node_csv


def extract_ladder_geometry(geometry, ladder, root="root", *, frame="auto"):
    """Extract a ladder from a trusted ROOT file using externally configured ROOT.

    Applies all ancestor transforms and saved volume-export placement through
    the existing extraction macro. Does not require PyROOT or modify the input.
    ``frame='auto'`` keeps this single ladder global; ``node`` uses its own frame.
    """
    with _extracted_csv(geometry, root) as (sensor_csv, node_csv):
        return load_ladder_geometry(
            sensor_csv, ladder, frame=frame, node_transforms=node_csv
        )


def extract_ladder_geometries(geometry, node, root="root", *, frame="auto"):
    """Extract every ladder below a node, running external ROOT only once.

    ``auto`` uses a selected UnitNNL/R half-unit as the common reference, global
    otherwise. ``global`` / ``node`` explicitly choose the reference frame.
    """
    with _extracted_csv(geometry, root) as (sensor_csv, node_csv):
        return load_ladder_geometries(
            sensor_csv, node, frame=frame, node_transforms=node_csv
        )


def _export_ladders(ladders, selected, directory, geometry):
    directory = directory.resolve()
    source = geometry.resolve()
    outputs = []
    seen = set()
    # Validate geometry and all destinations before writing the first file.
    for ladder in ladders:
        relative = (
            ladder.node_path.rsplit("/", 1)[-1]
            if ladder.node_path == selected
            else ladder.node_path[len(selected.rstrip("/")) + 1 :]
        )
        destination = directory.joinpath(*relative.split("/")).with_suffix(".json")
        resolved = destination.resolve()
        if not resolved.is_relative_to(directory):
            raise ValueError(f"Output path escapes the output directory: {destination}")
        if resolved == source:
            raise ValueError("Output must differ from the geometry input")
        key = str(resolved).casefold()
        if key in seen:
            raise ValueError(f"Conflicting ladder output paths: {destination}")
        seen.add(key)
        if destination.exists() and not destination.is_file():
            raise ValueError(f"Output is not a file: {destination}")
        payload = ladder.to_dict()
        payload["source_geometry"] = str(source)
        outputs.append(
            (destination, json.dumps(payload, indent=2, allow_nan=False) + "\n")
        )
    for destination, text in outputs:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text, encoding="utf-8")
    return tuple(str(destination) for destination, _ in outputs)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("geometry", type=Path, help="Input built ROOT geometry")
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument(
        "--node", help="Full ladder/parent path or unambiguous node name"
    )
    selection.add_argument(
        "--list", action="store_true", help="List ladder paths with sensors"
    )
    parser.add_argument(
        "--root", default="root", help="Externally configured ROOT executable"
    )
    parser.add_argument(
        "--frame",
        choices=("auto", "global", "node"),
        default="auto",
        help="auto: half-unit coordinates when --node is UnitNNL/R, global otherwise; node: selected node's frame",
    )
    destination = parser.add_mutually_exclusive_group()
    destination.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Single-ladder JSON file, relative to the working directory",
    )
    destination.add_argument(
        "--output-dir", type=Path, help="Write one JSON file per ladder below --node"
    )
    args = parser.parse_args(argv)
    if args.list and args.output_dir:
        parser.error("--output-dir requires --node, not --list")
    try:
        if args.output and args.output.resolve() == args.geometry.resolve():
            raise ValueError("Output must differ from the geometry input")
        with _extracted_csv(args.geometry, args.root) as (sensor_csv, node_csv):
            payload: dict[str, object]
            if args.list:
                payload = {"ladders": available_ladders(sensor_csv)}
            else:
                rows = _read_rows(sensor_csv)
                selected, paths = _select_ladder_paths(rows, args.node)
                if args.output_dir is None and selected not in paths:
                    raise ValueError(
                        "Parent nodes require --output-dir to write individual ladder files"
                    )
                reference = _reference_frame(selected, args.frame, node_csv)
                ladders = tuple(
                    _in_reference_frame(_load_ladder(rows, path), reference)
                    for path in paths
                )
                if args.output_dir is not None:
                    files = _export_ladders(
                        ladders, selected, args.output_dir, args.geometry
                    )
                    payload = {
                        "node_path": selected,
                        "ladder_count": len(ladders),
                        "files": files,
                        "coordinate_frame": "node" if reference else "global",
                    }
                    if reference is not None:
                        payload["reference_node"] = reference.node_path
                        payload["reference_to_global"] = reference.to_dict()
                else:
                    payload = ladders[0].to_dict()
            payload["source_geometry"] = str(args.geometry.resolve())
            text = json.dumps(payload, indent=2, allow_nan=False) + "\n"
        output = args.output
        if output is None:
            print(text, end="")
        else:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(text, encoding="utf-8")
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"geo-inspector ladder: {error}", file=sys.stderr)
        return 1
    return 0
