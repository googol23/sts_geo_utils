import unittest

from geo_inspector import local_bounds


class FakeBBox:
    def __init__(self):
        self.computed = False

    def ComputeBBox(self):
        self.computed = True

    def GetOrigin(self):
        return (1.0, 2.0, 3.0)

    def GetDX(self):
        return 0.5

    def GetDY(self):
        return 1.0

    def GetDZ(self):
        return 1.5

    def GetName(self):
        return "sensor_shape"


class ExtractSensorTests(unittest.TestCase):
    def test_tgeo_bbox_shape_is_its_own_bounding_box(self):
        shape = FakeBBox()

        self.assertEqual(
            local_bounds(shape),
            ((0.5, 1.0, 1.5), (1.5, 3.0, 4.5)),
        )
        self.assertTrue(shape.computed)


if __name__ == "__main__":
    unittest.main()
