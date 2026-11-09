"""Check working-directory defaults without writing into the package."""

import csv

from module_grades.plot_module_grades import main


def test_plot_cli_default_output_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    directory = tmp_path / "data/output"
    directory.mkdir(parents=True)
    source = directory / "module_geometry_grades.csv"
    rows = [
        dict(
            module_name=f"M{s}DL5B0",
            station=s,
            grade="A",
            x=10,
            y=20,
            dx=6,
            dy=2,
            r00=1,
            r01=0,
            r10=0,
            r11=1,
        )
        for s in range(8)
    ]
    with source.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    assert main(["--dpi", "10"]) == 0
    assert len(list(directory.glob("*.png"))) == 9
    assert not (directory / "data/output").exists()
