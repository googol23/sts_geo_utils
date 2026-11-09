import unittest

import numpy as np
from CameraView._renderer_core import _dimension_node_matches, _dimension_reference


class DimensionReferenceTests(unittest.TestCase):
    def setUp(self):
        self.indices = {"X": 0, "Y": 1, "Z": 2}

    def test_node_selector_matches_branch_and_descendants(self):
        self.assertTrue(
            _dimension_node_matches("Unit01R_3/Ladder_1/Sensor_0", "Unit01R_3/Ladder_1")
        )
        self.assertFalse(
            _dimension_node_matches(
                "Unit01R_3/Ladder_10/Sensor_0", "Unit01R_3/Ladder_1"
            )
        )

    def test_inner_radius_uses_transformed_local_radial_axis(self):
        angle = np.pi / 2
        rotation = np.array(
            [
                [np.cos(angle), -np.sin(angle), 0],
                [np.sin(angle), np.cos(angle), 0],
                [0, 0, 1],
            ]
        )
        translation = np.array([3.0, 4.0, 5.0])
        solid = {
            "vertices": np.array(
                [
                    [3.0, 4.0, 4.0],
                    [3.0, 4.0, 6.0],
                ]
            ),
            "rotation": rotation,
            "translation": translation,
            "inner_radius": 2.5,
        }

        point = _dimension_reference(
            {
                "shape": "tube",
                "instance": "closest_to_center",
                "point": "inner_radius",
                "radial_axis": "X",
            },
            [solid],
            self.indices,
        )

        np.testing.assert_allclose(point, [3.0, 6.5, 5.0])

    def test_inner_radius_requires_single_placed_solid(self):
        solid = {
            "vertices": np.zeros((1, 3)),
            "rotation": np.eye(3),
            "translation": np.zeros(3),
            "inner_radius": 1.0,
        }
        with self.assertRaisesRegex(ValueError, "one placed solid"):
            _dimension_reference(
                {"shape": "tube", "point": "inner_radius"},
                [solid, solid],
                self.indices,
            )

    def test_inner_radius_rejects_shapes_without_radius(self):
        solid = {
            "vertices": np.zeros((1, 3)),
            "rotation": np.eye(3),
            "translation": np.zeros(3),
            "inner_radius": None,
        }
        with self.assertRaisesRegex(ValueError, "has no inner radius"):
            _dimension_reference(
                {
                    "shape": "box",
                    "instance": "closest_to_center",
                    "point": "inner_radius",
                },
                [solid],
                self.indices,
            )


if __name__ == "__main__":
    unittest.main()
