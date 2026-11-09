"""STS geometry identity tests independent of grade data."""

import pytest
from geo_inspector.sts import parse_sensor_path

PATH = "/TOP_1/sts_v22d_1/Unit00R_1/LadderType0010_101/HalfLadder10t_1/HalfLadder10t_Module01_1/Sensor01_1"


@pytest.mark.parametrize(
    "path,key,name",
    [
        (PATH, (0, "R", 3, "T", 0), "M0DR1T0"),
        (
            PATH.replace(
                "Unit00R_1/LadderType0010_101", "Unit01R_3/LadderType1101_104"
            ),
            (0, "R", 0, "T", 0),
            "M1UR4T0",
        ),
        (
            PATH.replace(
                "Unit00R_1/LadderType0010_101", "Unit04R_9/LadderType0015_401"
            ),
            (3, "R", 6, "T", 0),
            "M4DR1T0",
        ),
        (
            PATH.replace(
                "Unit00R_1/LadderType0010_101", "Unit09L_20/LadderType1024_816"
            ),
            (7, "L", 7, "T", 0),
            "M9UL16T0",
        ),
    ],
)
def test_address_mapping(path, key, name):
    assert parse_sensor_path(path) == (key, name, 0)


def test_legacy_naming():
    path = PATH.replace("Unit00R_1/LadderType0010_101", "Unit04R_9/LadderType0015_401")
    assert parse_sensor_path(path, "STS8")[1] == "M3DR1T0"


def test_naming_uses_shared_implementation():
    from geo_inspector.sts import build_module_name_prefix
    from sts_utils.sts_naming import build_module_name_prefix as shared_prefix

    assert build_module_name_prefix is shared_prefix


def test_unknown_naming_scheme():
    with pytest.raises(ValueError, match="Unknown naming version"):
        parse_sensor_path(PATH, "unknown")
