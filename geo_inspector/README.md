# geo_inspector

A standalone Python package for inspecting saved ROOT TGeo geometries. Install this
project anywhere with its declared `sts-utils` dependency; the rest of the
`sts_tools` workspace is not required. Naming rules are imported from the shared
package, not copied into the inspector.

The package contains only geometry utilities:

- Load ROOT geometries and find/traverse their nodes.
- Extract sensor centres, local sizes and local-to-global orientation matrices.
- Calculate global axis-aligned sensor bounds.
- Select a ladder or parent node and export per-ladder sensor boxes as JSON.
- Decode legacy v22d and v26a STS sensor paths into positional module identities.

Grade joins, grade plots, table previews, ROOT geometry files and generated results
are **not part of this package**. Geometry inputs are arbitrary caller-supplied paths;
no ROOT file is stored in this project.

## Requirements

| Requirement                                                    | Used for                                      |
| -------------------------------------------------------------- | --------------------------------------------- |
| Python 3.10+ and its standard library                          | All Python utilities                          |
| sts-utils >= 0.1.0, < 0.2.0                                    | Shared STS naming conventions                 |
| Externally configured ROOT with TGeo and the `root` executable | `extract`, `ladder` and their extraction APIs |
| Externally configured PyROOT                                   | `bounds` and `open_geometry()`                |
| setuptools >= 61 and wheel                                     | Building/installing from source               |
| pytest >= 7                                                    | Optional development tests                    |

`sts-utils` is the only mandatory Python package dependency. It is maintained in
its own checkout and is not currently published to a package index; install it
from that checkout as shown below. ROOT is not installed or configured by pip.
Use your normal ROOT setup before extracting geometry. Matplotlib, pandas, VTK,
CameraView and FairRoot are not needed.
Only open trusted ROOT files: ROOT deserialization and macros are not sandboxed.

## Install

From a standalone checkout of this directory, create/activate an environment and
supply the path to your one shared utilities checkout (adjust it if moved):

```sh
python3 -m venv .venv
# Linux/macOS:
. .venv/bin/activate
# Windows PowerShell instead: .venv\Scripts\Activate.ps1
python -m pip install -e /u/dramirez/WORK/sts_tools/sts_utils .
```

For the PyROOT-based utilities, use an environment in which `import ROOT` works;
a new virtual environment does not necessarily inherit an existing PyROOT setup.
The external-executable `extract` command does not require PyROOT in Python.

Alternatively, from the `sts_tools` working directory, install both projects in
editable mode once per virtual environment:

```sh
python -m pip install -e ./sts_utils -e ./sts_geo_utils/geo_inspector
```

Each project/environment can point at this same utilities checkout. Changes to its
source take effect immediately; no copying or `PYTHONPATH` setup is needed. Changing
package metadata requires reinstalling. Editable installs share live changes: for
reproducible analyses, record the naming scheme and utilities Git commit, then use
a non-editable installation of that revision in a separate environment. See
[`sts-utils`](../../sts_utils/README.md) for the shared-library workflow.

After installation, both entry points work from any working directory:

```sh
geo-inspector --help
python -m geo_inspector --help
geo-inspector --version
```

With `sts-utils` installed, uninstalled inspector source usage also works: run
`python3 -m geo_inspector` from the parent `sts_geo_utils/` directory. The existing
`extraction.py` and `extract_sensors.py` also remain directly executable.

## Extract positions, local sizes and orientations

```sh
geo-inspector extract /path/to/sts_geo.root
geo-inspector extract /path/to/sts_geo.root --root /path/to/root --output sensors.csv
```

Default output: **`./data/output/sensors.csv`**, relative to the current working
directory. Relative `--output` names resolve under `./data/output`; an absolute
path overrides that directory. Parent directories are created automatically.
Input paths are relative to the current working directory. Inputs are not modified.

The bundled `extract_sts_sensors.C` macro runs ROOT in batch mode. It accepts a
saved `TGeoManager`, or a single exported `TGeoVolume` with a saved global placement
matrix. A volume export without a global placement matrix is rejected. Saved
placements are applied exactly once. Selected volumes must be named `SensorNN`
and have box shapes.

CSV columns:

- `node_path`: full hierarchy path, volume-rooted for volume-only exports.
- `x,y,z`: global sensor-box centre in **cm**, including the box origin and ancestor
  transformations.
- `dx,dy,dz`: **full local sensor dimensions**, in **cm**, twice ROOT's half lengths.
- `r00` through `r22`: row-major local-to-global orientation matrix. For a local
  displacement from the sensor centre, `global = centre + R * displacement`.

`extract_geometry(..., node_transforms="nodes.csv")` additionally writes node-to-global
poses: `node_path,x,y,z,r00,...,r22`. Here XYZ is the **node origin**, not the
shape's box centre. Both filenames are explicit working-directory-relative or
absolute paths; the API caller creates their parent directories. The usual
sensor CSV schema is unchanged. The macro's optional third argument names the
same node-transform CSV.

The macro can also run directly from this directory:

```sh
root -l -b -q 'extract_sts_sensors.C("/path/to/sts_geo.root")'
```

## Extract ladder sensor geometry

Use the **built ROOT geometry**, not layout YAML or database inventory. First
list the available ladder placements, then select one by its full hierarchy path
or by an exact node name that is unique in the file:

```sh
geo-inspector ladder /path/to/sts_geo.root --list
geo-inspector ladder /path/to/sts_geo.root --node Ladder_LadderType36_603 --output results/ladder.json
```

If a node name occurs more than once, the command fails and lists the matching
full paths. Pass one of those paths to `--node`. Legacy `LadderTypeNNNN` and v26a
`Ladder_LadderTypeNN` hierarchies are supported, including volume-rooted exports.
A ladder type/layout ID alone is **not** a placement identifier. Manufacturing
names and geometry-copy indices are not silently converted.

This command uses the existing external ROOT extraction macro; PyROOT is not
required. Saved global placements for volume exports and sensor-box origins are
handled exactly as for `extract`. A volume export without a saved global placement
is still rejected. Only ladders containing `SensorNN` boxes appear in `--list`.
The current implementation extracts the file once, then selects its ladders; it
never substitutes nominal dimensions or placements from `sts_geo_layout`.

`--output` is relative to the **working directory**, not `data/output`. Parent
directories are created automatically. Without it, JSON is written to stdout;
ROOT console messages go to stderr. Extraction/selection failure does not replace
an existing output file, and the geometry input cannot be used as output.

### Export all ladders below a parent node

A parent such as the half-unit `Unit04L_10` can be selected by its full path or
unique node name. Use **`--output-dir`** to write each descendant ladder to its
own JSON file:

```sh
geo-inspector ladder /path/to/sts_geo.root --node Unit04L_10 --output-dir results/Unit04L_10
```

For ladders directly below that half-unit, the output is:

```text
results/Unit04L_10/
  Ladder_LadderTypeNN_<copy>.json
  ...
```

Each file has exactly the same per-ladder schema described below, including its
full node path and the absolute `source_geometry` filename. ROOT runs **once**
for the complete batch, not once per ladder. All selected ladders are validated
before any files are written. The command prints a JSON summary containing
`node_path`, `ladder_count`, `files` (absolute output paths), `source_geometry`, and
`coordinate_frame`. Node-relative summaries also identify `reference_node` and
`reference_to_global`.

When selecting a higher-level ancestor, intermediate node names are retained as
subdirectories relative to the selected node. This prevents repeated ladder node
names in different units from overwriting one another. Selecting `/` exports all
sensor-bearing ladders while retaining their complete hierarchy. `--output-dir`
can also be used with a single ladder, producing `<ladder-node-name>.json`.

The directory is relative to the working directory and is created as needed.
`--output` and `--output-dir` are mutually exclusive; a parent node requires
`--output-dir`, even if it contains only one ladder. Ambiguous short parent names
are rejected rather than combined. As with ladder discovery, only branches with
sensor-bearing ladders are represented; empty nodes are not available from the
extraction CSV. Existing target JSON files are overwritten on success; unrelated
files are left alone. Filesystem write errors may leave a partially written batch.

### Coordinate reference

`--frame auto` is the default:

- Selecting a half-unit node (`UnitNNL/R_<copy>`, such as `Unit04L_10`) uses that
  **selected node's local coordinate system for every exported ladder**.
- Selecting a ladder, a higher-level ancestor, or `/` uses **global** coordinates.
  Selecting a ladder inside a half-unit does not implicitly select the unit frame.

Override the rule with `--frame global` or `--frame node`. `node` means the selected
node's local frame, including for a single ladder or a higher-level ancestor:

```sh
# Force global coordinates even when exporting a half-unit.
geo-inspector ladder /path/to/sts_geo.root --node Unit04L_10 --output-dir results/global --frame global
# Explicitly use the selected node as the reference.
geo-inspector ladder /path/to/sts_geo.root --node Unit04L_10 --output-dir results/local --frame node
```

All node transforms come from the built geometry. Positions are transformed by
the inverse node placement, sensor orientations are rotated into that frame, and
corners/bounds are recomputed there. **Full sensor-local dimensions do not change.**
This uses the node origin, not the centre of the half-unit's bounding box, and does
not re-centre each ladder independently. For an explicit root-node frame, select
the actual top-node path rather than the virtual `/` selector.

### JSON schemas

Global-coordinate files preserve **schema version 1**. Node-relative files use
**schema version 2** and add:

- `coordinate_frame: "node"`.
- `reference_node`: the full selected node path, identical for every ladder in the batch.
- `reference_to_global`: `translation` (XYZ in cm) and row-major 3x3 `rotation`, such
  that `global_point = translation + rotation @ reference_point`.

Both schemas contain:

- `schema_version`, `units: "cm"`, and `coordinate_frame`.
- `source_geometry`: absolute input filename (CLI output).
- `node_path`, `sensor_count`, and `sensors`, sorted by their full node paths.
- Per sensor: `node_path`, `center` (XYZ in the chosen reference frame), `dimensions`
  (full **sensor-local** XYZ lengths), and `rotation` (row-major 3x3 sensor-local to
  reference-frame orientation).
- Per sensor: eight reference-frame `corners`, ordered by local signs `(-,-,-)`, `(-,-,+)`,
  `(-,+,-)`, `(-,+,+)`, `(+,-,-)`, `(+,-,+)`, `(+,+,-)`, `(+,+,+)`.
- Per sensor and at ladder level: `bounds` with `min` and `max` XYZ corners
  of the axis-aligned bounding box in the chosen reference frame. Ladder bounds enclose **sensors only**, not
  supports, cables, or other material.

For a displacement `p` measured from the sensor-box centre in its own axes,
`reference_point = center + rotation @ p`. Consequently, the sensor-local dimensions
are not generally equal to the reference-frame bounding-box extents. This preserves
the oriented boxes needed for later point-cloud alignment; alignment itself is
not implemented here.

### Ladder Python API

```python
from geo_inspector import (
    extract_ladder_geometry, load_ladder_geometry, available_ladders,
    extract_ladder_geometries, load_ladder_geometries,
)

# From a trusted built ROOT file; requires the external root executable.
ladder = extract_ladder_geometry("sts_geo.root", "Ladder_LadderType36_603")
for sensor in ladder.sensors:
    print(sensor.node_path, sensor.center, sensor.dimensions)
    print(sensor.rotation, sensor.corners)
    print(sensor.bounds.minimum, sensor.bounds.maximum)
print(ladder.bounds.minimum, ladder.bounds.maximum)
payload = ladder.to_dict()  # JSON-compatible, without CLI source_geometry.

# Reuse an existing `geo-inspector extract` CSV without running ROOT again.
# Do not use a `bounds` CSV: it lacks local dimensions/orientations.
paths = available_ladders("sensors.csv")
if paths:
    ladder = load_ladder_geometry("sensors.csv", paths[0])

# Parent selection: each API returns a tuple of individual LadderGeometry objects.
# The ROOT API extracts the file just once, including node transforms.
# auto selects the given half-unit's frame; frame="global" overrides it.
ladders = extract_ladder_geometries("sts_geo.root", "Unit04L_10")
ladders = extract_ladder_geometries("sts_geo.root", "Unit04L_10", frame="global")

# Cache geometry and node poses together for ROOT-free node-frame loading.
from geo_inspector import extract_geometry
extract_geometry("sts_geo.root", "sensors.csv", node_transforms="nodes.csv")
ladders = load_ladder_geometries(
    "sensors.csv", "Unit04L_10", node_transforms="nodes.csv"
)
# An older sensor CSV alone can still be used explicitly in the global frame.
ladders = load_ladder_geometries("sensors.csv", "Unit04L_10", frame="global")
```

The API returns immutable `LadderGeometry`, `SensorGeometry` and `BoundingBox`
objects. A node-relative `LadderGeometry.reference_frame` is a `NodeFrame` holding
the reference node path and its node-to-global translation/rotation; global
objects have `reference_frame=None`. Both extraction and loading APIs accept
`frame="auto"`, `"global"`, or `"node"`. Node-frame CSV loading requires the
`node_transforms` file; missing transforms are never inferred from sensor poses.
CSV loading, corner/bounds calculation and JSON conversion need only the
standard library and the package's existing `sts-utils` dependency. Invalid or
non-finite dimensions, non-orthonormal orientations and duplicate sensor paths
are rejected rather than producing misleading alignment input.

## Extract global axis-aligned bounds

```sh
geo-inspector bounds /path/to/geometry.root --output bounds.csv
geo-inspector bounds /path/to/geometry.root --node /TOP_1/Unit00R_1
```

This replaces the removed top-level `extract_sensors.py` wrapper; the
implementation remains in `geo_inspector.extract_sensors`. From the `sts_geo_utils/`
directory, the same task can be run without installing the package:

```sh
python3 -m geo_inspector bounds /path/to/geometry.root --output bounds.csv
python3 -m geo_inspector bounds /path/to/geometry.root --node /TOP_1/Unit00R_1 --output unit_bounds.csv
```

For Python callers, replace `from extract_sensors import local_bounds, sensor_rows`
with `from geo_inspector import local_bounds, sensor_rows`. The CLI function is
available as `geo_inspector.extract_sensors.main` if needed.

Requires PyROOT. This selects sensor-like node/volume/shape names and transforms
their local bounding-box corners. CSV columns are `sensor,x,y,z,dx,dy,dz`, in ROOT
geometry units. Here dimensions are **global axis-aligned extents**, not the local
dimensions exported by `extract`.

Output defaults to stdout. An explicit output filename is relative to the working
directory, **not** `data/output`. The PyROOT loader preserves the former CameraView
volume-loading behavior; use `extract` to apply a separately saved global placement
matrix from a volume export.

## Python API

```python
from pathlib import Path
from geo_inspector import (
    extract_geometry, open_geometry, find_node, list_nodes, sensor_rows,
    parse_sensor_path,
)

# External ROOT: explicit output path, no PyROOT import.
Path("results").mkdir(exist_ok=True)
extract_geometry("geometry.root", "results/sensors.csv", root="root")

# PyROOT: keep the file open while using its objects.
root_file, geometry = open_geometry("geometry.root")
try:
    node = find_node(geometry.GetTopNode(), "/TOP_1/Unit00R_1")
    if node is not None:
        print([path for path, _ in list_nodes(node)])
    bounds = list(sensor_rows(geometry))
finally:
    root_file.Close()

# Pure Python; no ROOT environment or grade table needed.
path = (
    "/TOP_1/sts_v22d_1/Unit00R_1/LadderType0010_101/"
    "HalfLadder10t_1/HalfLadder10t_Module01_1/Sensor01_1"
)
key, module_prefix, sensor_index = parse_sensor_path(path)
assert module_prefix == "M0DR1T0"
```

`extract_geometry()` takes explicit working-directory-relative or absolute paths;
its caller provides the output directory. `find_node()` accepts paths with or
without the top-node name. `list_nodes()` yields `(path, node)` pairs depth-first.

`parse_sensor_path()` returns `((station, side, ladder, half, module), prefix,
sensor_index)`. The station and side-relative ladder indices are zero-based.
The positional prefix retains the geometry's slot numbering. STS3_5 naming is the
default; pass `naming_version="STS8"` for old names. No manufacturing serial suffix
is invented. Unsupported hierarchy layouts and naming versions raise `ValueError`.
The naming scheme is separate from the `sts-utils` package release and the packed
STS address encoding version.

## Development and packaging

From this directory, with the shared utilities checkout still in its current
workspace location:

```sh
python3 -m pip install -e ../../sts_utils -e '.[test]'
python3 -m pytest
python3 -m pip wheel --no-deps . --wheel-dir dist
```

Tests require pytest and the declared `sts-utils` dependency. The isolation test
copies only the inspector and uses the installed shared package, without sibling
workflows. The real-ROOT integration test
is skipped if `root` is unavailable. It checks nested transformations, a rotated
sensor with a nonzero box origin, ladder bounds and manager/volume-export agreement.
ROOT-free ladder tests also check oblique rotations, selection ambiguity, malformed
CSV input, JSON output and input-file protection.

The Python modules form the package directly; `pyproject.toml` explicitly maps
this project directory to the import name `geo_inspector`. Wheels include only
those modules and the ROOT macro, not external workflows, sample data, local
virtual environments or generated output. Generated output never defaults to
the installed package directory.

## Repository reorganization / migration

In the surrounding `sts_tools` workspace:

- Grade joins, plots, table preview and their reference data/tests live in
  `sts_geo_utils/module_grades/`. Its README documents the replacement commands for
  the former `geo-inspector inspect`, `plot` and `table` subcommands.
- ROOT geometry files are external inputs supplied by path; none are stored in this
  project or included in wheels.
- Existing generated grade tables/images live in
  `sts_geo_utils/module_grades/data/output/`.
- The former top-level `extract_sensors.py` compatibility wrapper was removed.
  Use `geo-inspector bounds` (or `python3 -m geo_inspector bounds`); see the
  global-bounds instructions above. `CameraView.geometry` still delegates to this
  package.

None of those sibling workflows is required to install or use `geo_inspector`.
The separately installed `sts-utils` package is required; its checkout can live
anywhere and is not located through the workspace directory structure.
