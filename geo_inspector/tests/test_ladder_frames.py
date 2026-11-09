"""Coordinate-frame regressions with nontrivial node translations and rotations."""

import csv
import json
import shutil

import pytest
from geo_inspector import (
    extract_ladder_geometries,
    extract_ladder_geometry,
    load_ladder_geometries,
    load_ladder_geometry,
)
from geo_inspector.cli import main
from geo_inspector.sts import NUMERIC_FIELDS, ROTATION_FIELDS

PARENT = "/TOP_1/sts_1"
UNIT = PARENT + "/Unit04L_10"
LADDER_A = UNIT + "/Ladder_LadderType36_601"
LADDER_B = UNIT + "/Ladder_LadderType37_602"
IDENTITY = (1, 0, 0, 0, 1, 0, 0, 0, 1)
UNIT_ROTATION = (0, -1, 0, 1, 0, 0, 0, 0, 1)
SENSOR_ROTATION = (0, -1, 0, 0, 0, 1, -1, 0, 0)
LOCAL_ROTATION = ((0, 0, 1), (0, 1, 0), (-1, 0, 0))
POSE_FIELDS = ("node_path", "x", "y", "z", *ROTATION_FIELDS)
SENSOR_FIELDS = ("node_path", *NUMERIC_FIELDS, *ROTATION_FIELDS)


def write_table(path, fields, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(fields)
        writer.writerows(rows)
    return path


@pytest.fixture
def geometry_csvs(tmp_path):
    # Unit-local sensor centres are (2,3,4) and (-2,1,-4).
    # The unit is rotated +90 degrees around Z and translated (10,20,30).
    sensors = write_table(
        tmp_path / "sensors.csv",
        SENSOR_FIELDS,
        [
            (LADDER_A + "/Module_0/Sensor01_0", 7, 22, 34, 6, 4, 0.2, *SENSOR_ROTATION),
            (LADDER_B + "/Module_0/Sensor02_0", 9, 18, 26, 2, 2, 0.2, *UNIT_ROTATION),
        ],
    )
    nodes = write_table(
        tmp_path / "nodes.csv",
        POSE_FIELDS,
        [
            (PARENT, 1, 2, 3, *IDENTITY),
            (UNIT, 10, 20, 30, *UNIT_ROTATION),
            (LADDER_A, 7, 20, 31, *IDENTITY),
            (LADDER_B, 9, 18, 26, *UNIT_ROTATION),
        ],
    )
    return sensors, nodes


@pytest.mark.parametrize("selector", [UNIT, UNIT + "/", "Unit04L_10"])
def test_half_unit_auto_frame_is_shared_by_all_ladders(geometry_csvs, selector):
    sensors, nodes = geometry_csvs
    ladders = load_ladder_geometries(sensors, selector, node_transforms=nodes)
    first, second = ladders
    box = first.sensors[0]
    assert box.center == pytest.approx((2, 3, 4))
    assert box.dimensions == (6, 4, 0.2)
    assert box.rotation == LOCAL_ROTATION
    assert box.bounds.minimum == pytest.approx((1.9, 1, 1))
    assert box.bounds.maximum == pytest.approx((2.1, 5, 7))
    assert second.sensors[0].center == pytest.approx((-2, 1, -4))
    assert second.sensors[0].rotation == ((1, 0, 0), (0, 1, 0), (0, 0, 1))
    assert first.reference_frame is second.reference_frame
    payload = first.to_dict()
    assert payload["schema_version"] == 2
    assert payload["coordinate_frame"] == "node"
    assert payload["reference_node"] == UNIT
    assert payload["reference_to_global"]["translation"] == (10, 20, 30)
    assert payload["reference_to_global"]["rotation"] == (
        (0, -1, 0),
        (1, 0, 0),
        (0, 0, 1),
    )


def test_each_local_corner_transforms_back_to_original_global_corner(geometry_csvs):
    sensors, nodes = geometry_csvs
    local = load_ladder_geometries(sensors, UNIT, node_transforms=nodes)
    global_ladders = load_ladder_geometries(sensors, UNIT, frame="global")
    for local_ladder, global_ladder in zip(local, global_ladders):
        reference = local_ladder.reference_frame
        assert reference is not None
        for local_box, global_box in zip(local_ladder.sensors, global_ladder.sensors):
            for local_corner, global_corner in zip(
                local_box.corners, global_box.corners
            ):
                restored = tuple(
                    reference.translation[i]
                    + sum(reference.rotation[i][j] * local_corner[j] for j in range(3))
                    for i in range(3)
                )
                assert restored == pytest.approx(global_corner)


@pytest.mark.parametrize("selector", [LADDER_A, PARENT, "/"])
def test_other_selections_remain_global_by_default(geometry_csvs, selector):
    sensors, nodes = geometry_csvs
    ladders = load_ladder_geometries(sensors, selector, node_transforms=nodes)
    assert ladders[0].sensors[0].center == (7, 22, 34)
    assert all(ladder.reference_frame is None for ladder in ladders)
    payload = ladders[0].to_dict()
    assert payload["schema_version"] == 1
    assert payload["coordinate_frame"] == "global"
    assert "reference_node" not in payload
    assert "reference_to_global" not in payload


def test_explicit_global_override_does_not_require_node_metadata(geometry_csvs):
    sensors, _ = geometry_csvs
    first, _ = load_ladder_geometries(sensors, UNIT, frame="global")
    assert first.sensors[0].center == (7, 22, 34)
    assert first.sensors[0].bounds.minimum == pytest.approx((5, 21.9, 31))
    assert first.reference_frame is None


def test_explicit_node_frame_for_non_unit_parent_and_single_ladder(geometry_csvs):
    sensors, nodes = geometry_csvs
    first, _ = load_ladder_geometries(
        sensors, PARENT, frame="node", node_transforms=nodes
    )
    assert first.sensors[0].center == (6, 20, 31)
    assert first.reference_frame.node_path == PARENT
    ladder = load_ladder_geometry(
        sensors, LADDER_A, frame="node", node_transforms=nodes
    )
    assert ladder.sensors[0].center == (0, 2, 3)
    assert ladder.reference_frame.node_path == LADDER_A


@pytest.mark.parametrize("mode", ["auto", "node"])
def test_node_frame_never_infers_missing_reference_from_sensors(geometry_csvs, mode):
    sensors, _ = geometry_csvs
    with pytest.raises(ValueError, match="require node transforms"):
        load_ladder_geometries(sensors, UNIT, frame=mode)


@pytest.mark.parametrize("mode", ["local", "parent", ""])
def test_invalid_frame_is_rejected(geometry_csvs, mode):
    sensors, nodes = geometry_csvs
    with pytest.raises(ValueError, match="Unsupported coordinate frame"):
        load_ladder_geometries(sensors, UNIT, frame=mode, node_transforms=nodes)


@pytest.mark.parametrize(
    "rows,message",
    [
        ([], "exactly one transform"),
        ([(UNIT, 0, 0, 0, *IDENTITY)] * 2, "exactly one transform"),
        ([(PARENT, 0, 0, 0, *IDENTITY)], "exactly one transform"),
        ([(UNIT, "nan", 0, 0, *IDENTITY)], "Non-finite reference"),
        ([(UNIT, "bad", 0, 0, *IDENTITY)], "Invalid reference"),
        ([(UNIT, 0, 0, 0, 2, 0, 0, 0, 1, 0, 0, 0, 1)], "not orthonormal"),
    ],
)
def test_invalid_node_metadata_is_rejected(tmp_path, geometry_csvs, rows, message):
    sensors, _ = geometry_csvs
    nodes = write_table(tmp_path / "invalid_nodes.csv", POSE_FIELDS, rows)
    with pytest.raises(ValueError, match=message):
        load_ladder_geometries(sensors, UNIT, node_transforms=nodes)


@pytest.fixture
def root_extractor(monkeypatch, geometry_csvs):
    import geo_inspector.ladder as module

    sensors, nodes = geometry_csvs
    calls = []

    def extract(geometry, output, root, *, stdout, node_transforms):
        calls.append((output, node_transforms))
        shutil.copyfile(sensors, output)
        shutil.copyfile(nodes, node_transforms)

    monkeypatch.setattr(module, "extract_geometry", extract)
    return calls


@pytest.mark.parametrize(
    "mode,expected", [(None, [2, 3, 4]), ("node", [2, 3, 4]), ("global", [7, 22, 34])]
)
def test_cli_exports_share_the_requested_frame(
    tmp_path, root_extractor, capsys, mode, expected
):
    output = tmp_path / "export"
    options = [] if mode is None else ["--frame", mode]
    assert (
        main(
            [
                "ladder",
                "geometry.root",
                "--node",
                "Unit04L_10",
                "--output-dir",
                str(output),
                *options,
            ]
        )
        == 0
    )
    files = sorted(output.glob("*.json"))
    payloads = [json.loads(path.read_text()) for path in files]
    assert len(payloads) == 2
    assert payloads[0]["sensors"][0]["center"] == expected
    summary = json.loads(capsys.readouterr().out)
    if mode == "global":
        assert summary["coordinate_frame"] == "global"
        assert all(payload["schema_version"] == 1 for payload in payloads)
    else:
        assert summary["coordinate_frame"] == "node"
        assert summary["reference_node"] == UNIT
        assert all(payload["reference_node"] == UNIT for payload in payloads)
        assert payloads[0]["reference_to_global"] == payloads[1]["reference_to_global"]
    assert len(root_extractor) == 1
    assert all(not path.exists() for path in root_extractor[0])


def test_root_apis_forward_frame_and_keep_single_ladder_global_by_default(
    root_extractor,
):
    first, _ = extract_ladder_geometries("geometry.root", UNIT)
    assert first.sensors[0].center == (2, 3, 4)
    first, _ = extract_ladder_geometries("geometry.root", UNIT, frame="global")
    assert first.sensors[0].center == (7, 22, 34)
    ladder = extract_ladder_geometry("geometry.root", LADDER_A)
    assert ladder.sensors[0].center == (7, 22, 34)
    ladder = extract_ladder_geometry("geometry.root", LADDER_A, frame="node")
    assert ladder.sensors[0].center == (0, 2, 3)
    assert len(root_extractor) == 4


def test_oblique_reference_recomputes_bounds_from_sensor_box_not_global_aabb(tmp_path):
    c = 2**-0.5
    rotation = (c, -c, 0, c, c, 0, 0, 0, 1)
    sensors = write_table(
        tmp_path / "sensors.csv",
        SENSOR_FIELDS,
        [
            (LADDER_A + "/Module_0/Sensor01_0", 10, 20, 30, 6, 2, 0.2, *rotation),
        ],
    )
    nodes = write_table(
        tmp_path / "nodes.csv",
        POSE_FIELDS,
        [
            (UNIT, 10, 20, 30, *rotation),
        ],
    )
    (local,) = load_ladder_geometries(sensors, UNIT, node_transforms=nodes)
    box = local.sensors[0]
    assert box.center == pytest.approx((0, 0, 0))
    assert box.bounds.minimum == pytest.approx((-3, -1, -0.1))
    assert box.bounds.maximum == pytest.approx((3, 1, 0.1))
    global_ladder = load_ladder_geometry(sensors, LADDER_A)
    assert global_ladder.bounds.minimum == pytest.approx((10 - 4 * c, 20 - 4 * c, 29.9))
