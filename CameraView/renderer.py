"""Canvas composition around caller-supplied per-pad camera renderers."""

from .layout import PadLayout


def render_scene(config, width, height, render_view, output=None, draw_dimensions=None,
                 background="white"):
    """Render configured camera views into one image.

    ``render_view(node, camera, (width, height), pad_id)`` returns a PIL image
    for a single pad. ``draw_dimensions(image, node, definitions, camera, pad_id)``
    is an optional in-place overlay callback. Camera and dimension data are
    sourced per pad from the loaded :class:`SceneConfig`.
    """
    from PIL import Image

    layout = PadLayout(config.layout)
    canvas = Image.new("RGB", (width, height), background)
    for pad_id, (x, y, pad_width, pad_height) in layout.bounds(width, height).items():
        camera = config.for_pad("cameras", pad_id)
        if not camera:
            raise ValueError("no camera configuration for pad %r" % pad_id)
        node_path = camera.get("node", config.data.get("geometry", {}).get("node"))
        if node_path is None:
            raise ValueError("no geometry node configured for pad %r" % pad_id)
        tile = render_view(node_path, camera, (pad_width, pad_height), pad_id)
        if tile.size != (pad_width, pad_height):
            tile = tile.resize((pad_width, pad_height))
        if draw_dimensions is not None:
            draw_dimensions(tile, node_path, config.for_pad("dimensions", pad_id), camera, pad_id)
        canvas.paste(tile, (x, y))
    if output is not None:
        canvas.save(output, dpi=tuple(config.render.get("dpi", (300, 300))))
    return canvas
