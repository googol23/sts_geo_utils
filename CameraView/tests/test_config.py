import unittest
from pathlib import Path

from CameraView.config import SceneConfig


class SceneConfigTests(unittest.TestCase):
    def test_alias_lookup(self):
        config = SceneConfig({
            "layout": {"matrix": ["1"], "aliases": {"front": "1"}},
            "cameras": {"front": {"direction": [0, 0, 1]}},
        })
        self.assertEqual(config.for_pad("cameras", "1")["direction"], [0, 0, 1])

    def test_requires_layout(self):
        with self.assertRaisesRegex(ValueError, "layout.matrix"):
            SceneConfig({})

    def test_workspace_scene_configs_load(self):
        config_dir = Path(__file__).resolve().parents[2] / "config"
        expected = {
            "capture_sts_cfSupport.json",
            "capture_sts_ladder.json",
            "capture_sts_station.json",
            "capture_sts_unit.json",
        }
        configs = {path.name: path for path in config_dir.glob("*.json")}
        self.assertEqual(set(configs), expected)

        for name, path in configs.items():
            with self.subTest(config=name):
                config = SceneConfig.load(path)
                self.assertTrue(config.data.get("geometry", {}).get("file"))
                self.assertTrue(config.cameras)


if __name__ == "__main__":
    unittest.main()
