"""Verify the relocated grade-join workflow and output convention."""

import csv

from module_grades.inspect_sts_geometry import ROTATION_FIELDS, main


def test_grade_cli_uses_working_directory(tmp_path, monkeypatch):
    path = (
        "/TOP_1/sts_v22d_1/Unit00R_1/LadderType0010_101/"
        "HalfLadder10t_1/HalfLadder10t_Module01_1/Sensor01_1"
    )
    source = tmp_path / "sensors.csv"
    row = dict(
        node_path=path,
        x=10,
        y=20,
        z=30,
        dx=6.2,
        dy=2.2,
        dz=0.032,
        **dict(zip(ROTATION_FIELDS, (1, 0, 0, 0, 1, 0, 0, 0, 1))),
    )
    with source.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=row)
        writer.writeheader()
        writer.writerow(row)
    grades = tmp_path / "grades.txt"
    grades.write_text(
        "station(unit) l/r ladder t/b module size grade\n0 R 3 T 0 2.2 C\n"
    )
    monkeypatch.chdir(tmp_path)
    assert main(["--sensor-csv", str(source), "--grades", str(grades)]) == 0
    with (tmp_path / "data/output/module_geometry_grades.csv").open() as stream:
        result = next(csv.DictReader(stream))
    assert result["module_name"] == "M0DR1T0"
    assert result["grade"] == "C"
    assert float(result["dy"]) == 2.2
