"""Command-line entry point for rendering CameraView scenes."""

import argparse
from pathlib import Path

from . import _renderer_core as backend
from . import find_node, open_geometry, render_scene
from .config import SceneConfig


def render_config(config_file, output=None, width=None, height=None):
    """Render a scene config using CameraView's bundled CPU renderer."""
    config_file = Path(config_file)
    config = SceneConfig.load(config_file)

    geometry_settings = config.data.get("geometry", {})
    geometry_file = geometry_settings.get("file")
    if not geometry_file:
        raise ValueError("configuration requires geometry.file")
    selected_output = output or config.render.get("output")
    if not selected_output:
        selected_output = config_file.with_suffix(".png")
    canvas_width = width or config.render.get("width", 1600)
    canvas_height = height or config.render.get("height", 1200)

    # All scene-specific values come from config; rendering tools are bundled
    # in CameraView._renderer_core.
    import ROOT
    import vtk

    ROOT.gROOT.SetBatch(True)
    backend.install_root_buffer_bridge(ROOT)
    setattr(backend, "DIMENSIONS", config.dimensions)
    style = config.render.get("dimension_style", {})
    style_names = {
        "font_size": "DIMENSION_FONT_SIZE",
        "color_rgb": "DIMENSION_COLOR",
        "line_width": "DIMENSION_LINE_WIDTH",
        "default_offset_px": "DIMENSION_OFFSET_PX",
        "extension_dash_px": "DIMENSION_EXTENSION_DASH_PX",
        "extension_width": "DIMENSION_EXTENSION_WIDTH",
        "extension_overhang_px": "DIMENSION_EXTENSION_OVERHANG_PX",
        "arrow_length_px": "DIMENSION_ARROW_LENGTH_PX",
        "arrow_half_width_px": "DIMENSION_ARROW_HALF_WIDTH_PX",
    }
    for key, attribute in style_names.items():
        if key in style:
            value = style[key]
            if isinstance(value, list) and (key.endswith("_px") or key == "color_rgb"):
                value = tuple(value)
            setattr(backend, attribute, value)
    typography = config.render.get("typography", {})
    for key, attribute in {
        "tick_label_font_size": "TICK_LABEL_FONT_SIZE",
        "pad_title_font_size": "PAD_TITLE_FONT_SIZE",
        "axis_title_font_size": "AXIS_TITLE_FONT_SIZE",
    }.items():
        if key in typography:
            setattr(backend, attribute, typography[key])

    file_handle, geometry = open_geometry(geometry_file, ROOT)
    try:
        actors_by_path = {}
        projections_by_pad = {}

        def actors_for(node_path):
            key = (
                tuple(node_path.split("/"))
                if isinstance(node_path, str)
                else tuple(node_path)
            )
            if key not in actors_by_path:
                node = find_node(geometry.GetTopNode(), node_path)
                if node is None:
                    raise ValueError(f"geometry node not found: {node_path}")
                excluded_shapes = geometry_settings.get("exclude_shapes", ())
                included_nodes = geometry_settings.get("include_nodes")
                actors = backend.build_actors(
                    ROOT,
                    vtk,
                    node,
                    None,
                    exclude_shapes=excluded_shapes,
                    include_nodes=included_nodes,
                )
                if not actors:
                    raise RuntimeError(
                        f"no renderable solids found at geometry node {node_path}"
                    )
                actors_by_path[key] = (actors, backend.collect_triangles(vtk, actors))
            return actors_by_path[key]

        def render_view(node_path, camera, size, pad_id):
            _, (batches, points) = actors_for(node_path)
            direction = camera.get("direction", (1, -1, 0.85))
            up = camera.get("up", (0, 1, 0))
            perspective = bool(camera.get("perspective", False))
            expected_axes = camera.get("grid_axes")
            axis_names = None
            if expected_axes and not perspective:
                axis_names = backend.camera_screen_axes(direction, up, expected_axes)
            tile, _, projection = backend.cpu_tile(
                batches,
                points,
                direction,
                up,
                perspective=perspective,
                width=size[0],
                height=size[1],
                grid=axis_names is not None,
                axis_names=axis_names,
                zoom=camera.get("zoom", 1.0),
            )
            projections_by_pad[pad_id] = projection
            from PIL import ImageDraw

            title_font = backend.load_font(backend.PAD_TITLE_FONT_SIZE)
            ImageDraw.Draw(tile).text(
                (14, 14),
                camera.get("title", str(pad_id)),
                fill=(30, 38, 49),
                font=title_font,
            )
            return tile

        def draw_dimensions(tile, node_path, definitions, camera, pad_id):
            if definitions:
                actors, _ = actors_for(node_path)
                # The legacy overlay reads its definitions from this module map.
                backend.DIMENSIONS[pad_id] = definitions
                if camera.get("grid_axes") and not camera.get("perspective", False):
                    direction = camera.get("direction", (1, -1, 0.85))
                    up = camera.get("up", (0, 1, 0))
                    axes = backend.camera_screen_axes(
                        direction, up, camera["grid_axes"]
                    )
                    if axes is not None:
                        backend.draw_dimension_overlays(
                            tile, pad_id, projections_by_pad[pad_id], actors
                        )

        image = render_scene(
            config,
            canvas_width,
            canvas_height,
            render_view,
            output=selected_output,
            draw_dimensions=draw_dimensions,
            background=config.render.get("background", "white"),
        )
        return image, selected_output
    finally:
        file_handle.Close()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Render a CameraView scene config")
    parser.add_argument("config", help="scene configuration (.json, .yaml, or .yml)")
    parser.add_argument("-o", "--output", help="output image path (overrides config)")
    parser.add_argument("--width", type=int, help="output canvas width in pixels")
    parser.add_argument("--height", type=int, help="output canvas height in pixels")
    args = parser.parse_args(argv)
    _, output = render_config(args.config, args.output, args.width, args.height)
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
