import unittest

from CameraView.config import SceneConfig
from CameraView.renderer import render_scene


class RenderSceneTests(unittest.TestCase):
    def test_camera_node_overrides_geometry_node_per_pad(self):
        config = SceneConfig({
            "geometry": {"node": "/World/default"},
            "layout": {"matrix": ["12"]},
            "cameras": {
                "1": {"direction": [0, 0, 1], "node": "/World/custom"},
                "2": {"direction": [0, 0, 1]},
            },
        })
        rendered_nodes = {}

        def render_view(node_path, camera, size, pad_id):
            from PIL import Image

            rendered_nodes[pad_id] = node_path
            return Image.new("RGB", size)

        render_scene(config, 20, 10, render_view)

        self.assertEqual(rendered_nodes, {"1": "/World/custom", "2": "/World/default"})


if __name__ == "__main__":
    unittest.main()
