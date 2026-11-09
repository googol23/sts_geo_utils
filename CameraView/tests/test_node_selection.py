import unittest

from CameraView._renderer_core import node_path_is_included, normalize_node_paths


class NodeSelectionTests(unittest.TestCase):
    def test_paths_are_normalized_to_relative_segments(self):
        self.assertEqual(
            normalize_node_paths(["Unit00R_1", "Unit01L_4/Ladder_1"]),
            (("Unit00R_1",), ("Unit01L_4", "Ladder_1")),
        )

    def test_selected_node_and_descendants_are_included(self):
        selected = normalize_node_paths(["Unit00R_1/Ladder_1"])
        self.assertTrue(node_path_is_included(("Unit00R_1", "Ladder_1"), selected))
        self.assertTrue(
            node_path_is_included(("Unit00R_1", "Ladder_1", "Sensor_1"), selected)
        )

    def test_unselected_sibling_branches_are_not_included(self):
        selected = normalize_node_paths(["Unit00R_1/Ladder_1"])
        self.assertFalse(node_path_is_included(("Unit00R_1",), selected))
        self.assertFalse(node_path_is_included(("Unit00R_1", "Ladder_2"), selected))

    def test_empty_selection_includes_every_node(self):
        self.assertTrue(node_path_is_included(("Unit00R_1",), ()))

    def test_invalid_paths_are_rejected(self):
        with self.assertRaises(ValueError):
            normalize_node_paths("Unit00R_1")
        with self.assertRaises(ValueError):
            normalize_node_paths(["Unit00R_1/../Unit01L_4"])


if __name__ == "__main__":
    unittest.main()
