# Module-grade workflows

These repository scripts combine geometry information with STS module-quality
grades, plot grade distributions and preview CSV tables. They were moved out of
`geo_inspector` because they are analysis workflows, not core geometry inspection.
The dependency is one-way: these scripts use `geo_inspector`, not vice versa.

## Setup

From the `sts_tools` repository root:

```sh
python3 -m pip install ./sts_geo_utils/geo_inspector
python3 -m pip install -r sts_geo_utils/module_grades/requirements.txt
```

Python 3.10+ is required. Matplotlib is needed only for plots; pandas only for the
table viewer. CSV joins use the standard library plus `geo_inspector`. Using a
ROOT geometry directly requires an externally configured ROOT executable, not
FairRoot or PyROOT in Python.

## Join geometry and grades

Run from this directory so relative output names use its `data/output` directory:

```sh
python3 inspect_sts_geometry.py --geometry /path/to/sts_geometry.root --include-path
# Or use a previously extracted sensor CSV:
python3 inspect_sts_geometry.py --sensor-csv /path/to/sensors.csv --include-path
```

Default grades: `data/input/uli_new_grades.txt` beside these scripts. Override with
`--grades /path/to/grades.txt`; the supplied table is a v22d reference, not a
universal table for every geometry version. Use `--root /path/to/root` to select
an executable. The join's temporary extraction CSV is removed afterwards.

Default output: `./data/output/module_geometry_grades.csv`. Relative `--output`
names resolve under `./data/output`, relative to the working directory; absolute
paths override it. Explicit input paths are working-directory-relative. The final
CSV is replaced only after validation succeeds.

Geometry columns retain the `geo_inspector extract` schema: global centres, full
local dimensions in cm and row-major orientation matrices. The join adds
`module_name,station,side,ladder,half,module,grade`. `--include-path` retains
`node_path`. `--naming-version STS8` selects legacy positional names. Duplicate,
missing/unused grades and invalid geometry are rejected. Grade-table sensor-size
discrepancies produce warnings; geometry dimensions remain authoritative.

## Plots and table preview

```sh
python3 plot_module_grades.py
python3 plot_module_grades.py --dpi 150 --output-dir plots
python3 inspect_module_table.py --rows 20
```

Default source: `./data/output/module_geometry_grades.csv`. Plotting writes eight
station XY projections and `all_stations_xy.png`, with common limits and equal
axis scales. The sensor faces use local sizes and orientations; z separation is
collapsed, so projections may overlap. Default resolution is 300 DPI. Adjust
`GRADE_PALETTE` in the plot script to change colours. Unknown grades, invalid
values and missing stations are rejected. A relative `--output-dir` resolves under
`./data/output`; absolute paths override it.

The table viewer loads every CSV column, lists the available columns and prints
ten rows by default. Edit `PRINT_COLUMNS` to select displayed columns. Zero rows
is allowed; negative limits are rejected.

From the parent `sts_geo_utils/` directory the equivalent module entry points are
`python3 -m module_grades.inspect_sts_geometry`,
`python3 -m module_grades.plot_module_grades` and
`python3 -m module_grades.inspect_module_table`. Their working-directory-relative
output convention still applies.

## Data and tests

The existing reference grade table, `.geo.info` description, captured node-path
fixture and previously generated output are kept with this workflow. ROOT geometry
files are not stored in this project; pass the file to inspect with `--geometry`.

After installing pytest, run from `sts_geo_utils/`:

```sh
python3 -m pytest module_grades/tests
```

The 876-row capture validates geometry-to-grade matching with synthetic test
coordinates. Real ROOT coordinate tests belong to `geo_inspector/tests`.

## Command migration

| Former package command | Replacement from this directory |
| --- | --- |
| `geo-inspector inspect ...` | `python3 inspect_sts_geometry.py ...` |
| `geo-inspector plot ...` | `python3 plot_module_grades.py ...` |
| `geo-inspector table ...` | `python3 inspect_module_table.py ...` |

The former `geo_inspector.inspect_sts_geometry` imports now live in
`module_grades.inspect_sts_geometry`. Pure geometry path decoding lives in
`geo_inspector.sts` and is also exported as `geo_inspector.parse_sensor_path`.
