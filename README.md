# STS geometry utilities

Utilities for inspecting, rendering, and analyzing STS detector geometry.
Geometry ROOT files are external inputs supplied by path; this repository does not
store them.

## Components

- [`geo_inspector`](geo_inspector/README.md): installable package and CLI for ROOT
  TGeo navigation, sensor extraction, bounds, and ladder exports.
- [`CameraView`](CameraView/README.md): configurable geometry scene rendering using
  `geo_inspector` for navigation.
- [`module_grades`](module_grades/README.md): geometry/grade joins, plots, and table
  inspection workflows.
- [`config`](config/): CameraView scene configurations.

## Setup

Python 3.10+ and the sibling `sts-utils` package are required. From this repository:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e /path/to/sts_utils -e './geo_inspector[test]'
python -m pip install -r module_grades/requirements.txt
```

ROOT is configured externally. CameraView rendering additionally requires PyROOT,
VTK, NumPy, and Pillow.

## Use and test

```sh
geo-inspector --help
python -m CameraView config/capture_sts_cfSupport.json
python -m pytest geo_inspector/tests CameraView/tests module_grades/tests
```

See each component README for command details, schemas, dependencies, and runtime
requirements.
