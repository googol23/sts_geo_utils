import unittest

from CameraView._renderer_core import format_dimension_label


class DimensionLabelTests(unittest.TestCase):
    def test_name_is_used_in_default_label(self):
        label = format_dimension_label({"name": "Sensor pitch"}, 3.2, "Z")
        self.assertEqual(label, "Sensor pitch = 3.20 cm")

    def test_axis_is_fallback_when_name_is_missing(self):
        label = format_dimension_label({}, 1.25, "Y")
        self.assertEqual(label, "Y = 1.25 cm")

    def test_explicit_higher_precision_is_preserved(self):
        label = format_dimension_label({"label": "{value:.3f} cm"}, 1.2345, "Y")
        self.assertEqual(label, "1.234 cm")

    def test_explicit_label_template_is_preserved(self):
        label = format_dimension_label(
            {"name": "Sensor pitch", "label": "{name}: {axis}={value:.1f} cm"},
            3.2,
            "Z",
        )
        self.assertEqual(label, "Sensor pitch: Z=3.2 cm")


if __name__ == "__main__":
    unittest.main()
