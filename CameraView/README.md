# CameraView

A small, reusable package for describing geometry scenes, locating TGeo nodes,
partitioning a canvas into camera pads, and composing per-pad render output.

Geometry loading and navigation are provided by the sibling
[`geo_inspector`](../geo_inspector/README.md) package. Existing CameraView imports
remain supported. Running from `sts_geo_utils/` uses the local inspector; outside that
source tree, install it with `python3 -m pip install ./sts_geo_utils/geo_inspector`
from the repository root. Rendering dependencies are not needed for inspection.

## Layout and configuration

A matrix cell is one unit of canvas area. Repeated characters form a pad and
must be contiguous in a rectangle. For example, `11122 / 33322 / 44422`
creates three left pads, each 3/5 of the canvas width, and one right pad 2/5
wide. Matrix identifiers are pad IDs; `layout.aliases` maps descriptive names
onto those IDs, and camera/dimension sections may use either key.

```yaml
geometry:
  file: /path/to/geometry.geo.root
  node: /World/Unit00R_1/Ladder_LadderType09_101
layout:
  matrix: ["11122", "33322", "44422"]
  aliases:
    "1": perspective
    "2": overview
cameras:
  "1":
    node: /World/Unit00R_1/Ladder_LadderType09_101
    direction: [1, -1, 0.85]
    up: [0, 1, 0]
    zoom: 1.0
    perspective: true
  "2":
    direction: [0, 0, 1]
    up: [1, 0, 0]
    zoom: 2.0
    perspective: false
    grid_axes: [X, Y]
dimensions:
  "2":
    - name: Sensor pitch
      axis: Z
      from: { shape: Sensor01Shp, instance: bottommost, point: center }
      to: { shape: Sensor02Shp, instance: bottommost, point: center }
    - name: Tube inner radius
      axis: R
      from: { shape: TubeShape, instance: closest_to_center, point: center }
      to:
        {
          shape: TubeShape,
          instance: closest_to_center,
          point: inner_radius,
          radial_axis: X,
        }
render:
  dpi: [300, 300]
```

A camera's optional `node` overrides `geometry.node` for that pad, allowing
pads to render different geometry nodes. Cameras without `node` keep using the
scene-level `geometry.node`.

Set `geometry.include_nodes` to render only selected branches below the chosen
geometry node. Paths are relative to that node, and selecting a node includes
all of its descendants. Ancestors are still traversed to retain each selected
branch's placement transform. For example, to render just two station units:

```yaml
geometry:
  node: /
  include_nodes:
    - Unit00R_1
    - Unit01L_4
  exclude_shapes:
    - base_segments_bbox
```

`include_nodes` paths may contain `/` to identify nested nodes (for example,
`Unit00R_1/Ladder_LadderType09_101`). A missing selected path raises an error.
`exclude_shapes` remains a separate filter for TGeo shape names; it does not
select or exclude node branches. A dimension endpoint may also specify `node`
to restrict its `shape` lookup to that node branch (including descendants). For
example, use `node: Unit00R_1/Ladder_1` with `shape: Sensor01Shp`; `shape` must
always be the TGeo shape name, not a geometry node path.

For TGeo tube shapes, a dimension endpoint may use `point: inner_radius` to
reference `GetRmin()`. Its optional `radial_axis` (`X` or `Y`, default `X`) picks
a radial direction in the tube's local frame; the placement rotation is applied
when drawing. Set `axis: R` to label the measured value as a radius. Choose a
camera that shows the selected radial direction; the dimension value remains the
true radius even if the view foreshortens its drawn line. Select one placement
with `instance` (for example, `closest_to_center`), since `all` is ambiguous for
a radius endpoint.

JSON is also supported. YAML files require optional `PyYAML`; JSON and all
configuration/layout utilities use only the Python standard library.

## Command line

The workspace scene configurations live in the sibling `config/` directory. From
`sts_geo_utils`, render one with:

```sh
python3 -m CameraView config/capture_sts_cfSupport.json
```

The same command accepts `capture_sts_ladder.json`, `capture_sts_station.json`, or
`capture_sts_unit.json`. Their `geometry.file` values are environment-specific;
update those paths if the corresponding ROOT geometry is stored elsewhere.
Override output or canvas size with `--output`, `--width`, and `--height`.
The package contains its own TGeo mesh conversion, CPU rasterizer, and dimension
overlay implementation in `_renderer_core.py`; it does not import either
standalone capture script. Rendering requires PyROOT, VTK, NumPy, and Pillow. A scene may set
`geometry.exclude_shapes` to skip named solids during meshing; descendants of
an excluded volume are still traversed and rendered.

## API

```python
from CameraView import SceneConfig, open_geometry, find_node, list_nodes, render_scene

config = SceneConfig.load("scene.yaml")
root_file, geometry = open_geometry(config.data["geometry"]["file"])
try:
    node = find_node(geometry.GetTopNode(), config.data["geometry"]["node"])
    if node is None:
        raise ValueError("configured node not found")
    print([path for path, _ in list_nodes(node)])

    # Custom rasterizer callbacks can still be supplied through the API.
    image = render_scene(
        config, 1600, 1200,
        render_view=my_camera_renderer,
        draw_dimensions=my_dimension_overlay,
        output="scene.png",
    )
finally:
    root_file.Close()
```

`render_view(node_path, camera_config, (width, height), pad_id)` returns a PIL
image for one pad. The optional dimension callback receives
`(image, node_path, dimension_definitions, camera_config, pad_id)` and can
apply a custom overlay. The CLI uses the package's bundled rasterizer and
overlay. PyROOT, VTK, NumPy, and Pillow are imported only when rendering.

Run unit tests from `sts_geo_utils` with:

```sh
python -m unittest discover -s CameraView/tests
```
