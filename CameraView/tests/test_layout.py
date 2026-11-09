import unittest

from CameraView.layout import PadLayout


class PadLayoutTests(unittest.TestCase):
    def test_example_proportions_and_rows(self):
        layout = PadLayout(["11122", "33322", "44422"])
        bounds = layout.bounds(1000, 600)
        self.assertEqual(bounds["1"], (0, 0, 600, 200))
        self.assertEqual(bounds["3"], (0, 200, 600, 200))
        self.assertEqual(bounds["4"], (0, 400, 600, 200))
        self.assertEqual(bounds["2"], (600, 0, 400, 600))

    def test_alias_identifiers_and_uneven_pixels(self):
        layout = PadLayout(["aaB", "ccB"])
        bounds = layout.bounds(7, 5)
        self.assertEqual(set(bounds), {"a", "B", "c"})
        self.assertEqual(sum(rect[2] * rect[3] for rect in bounds.values()), 35)

    def test_non_rectangular_pad_rejected(self):
        with self.assertRaisesRegex(ValueError, "rectangle"):
            PadLayout(["aba", "aaa"])

    def test_bad_matrix_rejected(self):
        for matrix in ([], [""], ["12", "1"]):
            with self.subTest(matrix=matrix), self.assertRaises(ValueError):
                PadLayout(matrix)


if __name__ == "__main__":
    unittest.main()
