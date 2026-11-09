"""Ladder selection and box geometry, without a ROOT installation."""

import csv
import json
import math

import pytest
from geo_inspector import (
    available_ladders,
    extract_ladder_geometries,
    extract_ladder_geometry,
    load_ladder_geometries,
    load_ladder_geometry,
)
from geo_inspector.cli import main
from geo_inspector.sts import NUMERIC_FIELDS, ROTATION_FIELDS

LADDER = "/TOP_1/sts_1/Unit00R_1/Ladder_LadderType36_101"
OTHER = "/TOP_1/sts_1/Unit01R_2/Ladder_LadderType36_101"
IDENTITY = (1, 0, 0, 0, 1, 0, 0, 0, 1)


def sensor(path, center=(10, 20, 30), dimensions=(6.2, 2.2, 0.03), rotation=IDENTITY):
    return dict(
        zip(
            ("node_path", *NUMERIC_FIELDS, *ROTATION_FIELDS),
            (path, *center, *dimensions, *rotation),
        )
    )


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream, ("node_path", *NUMERIC_FIELDS, *ROTATION_FIELDS)
        )
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_rotated_sensor_corners_and_aggregate_bounds(tmp_path):
    # 45 degrees distinguishes local dimensions from global AABB extents.
    c = math.sqrt(0.5)
    rotation = (c, -c, 0, c, c, 0, 0, 0, 1)
    csv_path = write_csv(
        tmp_path / "sensors.csv",
        [
            sensor(LADDER + "/HalfLadder_0/Module100_3/Sensor04_0", rotation=rotation),
            sensor(LADDER + "/HalfLadder_1/Module100_0/Sensor04_0", center=(0, 0, 0)),
            sensor(
                OTHER + "/HalfLadder_0/Module100_3/Sensor04_0", center=(100, 100, 100)
            ),
        ],
    )
    ladder = load_ladder_geometry(csv_path, LADDER)
    assert ladder.node_path == LADDER
    assert len(ladder.sensors) == 2
    box = ladder.sensors[0]
    assert box.center == (10, 20, 30)
    assert box.dimensions == (6.2, 2.2, 0.03)
    assert box.rotation[0] == pytest.approx((c, -c, 0))
    assert len(set(box.corners)) == 8
    assert box.corners[0] == pytest.approx((10 - 2 * c, 20 - 4.2 * c, 29.985))
    assert box.bounds.minimum == pytest.approx((10 - 4.2 * c, 20 - 4.2 * c, 29.985))
    assert box.bounds.maximum == pytest.approx((10 + 4.2 * c, 20 + 4.2 * c, 30.015))
    assert ladder.bounds.minimum == pytest.approx((-3.1, -1.1, -0.015))
    assert ladder.bounds.maximum == pytest.approx((10 + 4.2 * c, 20 + 4.2 * c, 30.015))
    payload = json.loads(json.dumps(ladder.to_dict(), allow_nan=False))
    assert payload["units"] == "cm"
    assert payload["coordinate_frame"] == "global"
    assert payload["schema_version"] == 1
    assert payload["sensor_count"] == 2
    assert len(payload["sensors"][0]["corners"]) == 8


@pytest.mark.parametrize(
    "path",
    [
        LADDER,
        "/TOP_1/Unit00R_1/LadderType0010_101",
        "/LadderType0010",
        "/Ladder_LadderType36",
    ],
)
def test_supported_ladder_hierarchies_and_volume_exports(tmp_path, path):
    source = write_csv(
        tmp_path / "sensors.csv", [sensor(path + "/Module_0/Sensor01_0")]
    )
    assert available_ladders(source) == (path,)
    assert load_ladder_geometry(source, path.rsplit("/", 1)[-1]).node_path == path
    assert load_ladder_geometry(source, path + "/").node_path == path


def test_ambiguous_missing_and_prefix_selection(tmp_path):
    source = write_csv(
        tmp_path / "sensors.csv",
        [
            sensor(LADDER + "/Module_0/Sensor04_0"),
            sensor(OTHER + "/Module_0/Sensor04_0"),
            sensor(LADDER + "0/Module_0/Sensor04_0"),
        ],
    )
    assert len(available_ladders(source)) == 3
    with pytest.raises(ValueError, match="Ambiguous ladder"):
        load_ladder_geometry(source, "Ladder_LadderType36_101")
    with pytest.raises(ValueError, match="Ladder not found"):
        load_ladder_geometry(source, "Ladder_LadderType36_10")
    assert len(load_ladder_geometry(source, LADDER).sensors) == 1


def test_duplicate_sensor_is_rejected(tmp_path):
    row = sensor(LADDER + "/Module_0/Sensor04_0")
    source = write_csv(tmp_path / "sensors.csv", [row, row])
    with pytest.raises(ValueError, match="Duplicate sensor"):
        load_ladder_geometry(source, LADDER)


@pytest.mark.parametrize(
    "field,value,message",
    [
        ("x", "nan", "Non-finite"),
        ("y", "inf", "Non-finite"),
        ("dx", "-1", "non-positive"),
        ("dz", "0", "non-positive"),
        ("r00", "2", "not orthonormal"),
        ("z", "invalid", "Invalid sensor geometry"),
        ("node_path", "relative/Sensor04_0", "Invalid absolute"),
    ],
)
def test_invalid_sensor_geometry(tmp_path, field, value, message):
    row = sensor(LADDER + "/Module_0/Sensor04_0")
    row[field] = value
    source = write_csv(tmp_path / "sensors.csv", [row])
    with pytest.raises(ValueError, match=message):
        load_ladder_geometry(source, LADDER)


def test_bounds_csv_is_not_mistaken_for_local_dimensions(tmp_path):
    source = tmp_path / "bounds.csv"
    source.write_text("sensor,x,y,z,dx,dy,dz\npath,0,0,0,6.2,2.2,.03\n")
    with pytest.raises(ValueError, match="missing columns"):
        load_ladder_geometry(source, LADDER)


def test_empty_extraction(tmp_path):
    source = write_csv(tmp_path / "empty.csv", [])
    assert available_ladders(source) == ()
    with pytest.raises(ValueError, match="Ladder not found"):
        load_ladder_geometry(source, LADDER)


def write_extraction(output, rows, node_transforms):
    write_csv(output, rows)
    paths = set()
    for row in rows:
        names = row["node_path"].strip("/").split("/")
        paths.update("/" + "/".join(names[:i]) for i in range(1, len(names) + 1))
    fields = ("node_path", "x", "y", "z", *ROTATION_FIELDS)
    with node_transforms.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fields)
        writer.writeheader()
        writer.writerows(
            dict(zip(fields, (path, 0, 0, 0, *IDENTITY))) for path in sorted(paths)
        )


@pytest.fixture
def fake_extraction(monkeypatch):
    import geo_inspector.ladder as module

    calls = []

    def extract(geometry, output, root, *, stdout, node_transforms):
        calls.append((geometry, output, root, stdout))
        print("ROOT diagnostics", file=stdout)
        write_extraction(
            output, [sensor(LADDER + "/Module100_3/Sensor04_0")], node_transforms
        )

    monkeypatch.setattr(module, "extract_geometry", extract)
    return calls


def test_extraction_api_cleans_temporary_csv(tmp_path, fake_extraction):
    source = tmp_path / "geometry.root"
    result = extract_ladder_geometry(source, LADDER, root="configured-root")
    assert result.node_path == LADDER
    assert fake_extraction[0][0] == source
    assert fake_extraction[0][2] == "configured-root"
    assert not fake_extraction[0][1].exists()


def test_cli_stdout_is_json_and_list_is_discoverable(tmp_path, fake_extraction, capsys):
    source = tmp_path / "geometry.root"
    assert main(["ladder", str(source), "--list"]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["ladders"] == [LADDER]
    assert "ROOT diagnostics" in captured.err
    assert main(["ladder", str(source), "--node", LADDER]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["source_geometry"] == str(source.resolve())
    assert payload["sensors"][0]["node_path"].endswith("/Module100_3/Sensor04_0")


def test_cli_output_paths_and_failure_preserves_existing_output(
    tmp_path, fake_extraction, capsys
):
    source = tmp_path / "geometry.root"
    source.write_bytes(b"untouched geometry")
    output = tmp_path / "results" / "ladder.json"
    assert main(["ladder", str(source), "--node", LADDER, "-o", str(output)]) == 0
    original = output.read_bytes()
    assert json.loads(original)["sensor_count"] == 1
    assert main(["ladder", str(source), "--node", "missing", "-o", str(output)]) == 1
    assert output.read_bytes() == original
    assert main(["ladder", str(source), "--node", LADDER, "-o", str(source)]) == 1
    assert "Output must differ" in capsys.readouterr().err
    assert source.read_bytes() == b"untouched geometry"
    assert len(fake_extraction) == 2


def test_cli_reports_missing_root(tmp_path, monkeypatch, capsys):
    import geo_inspector.extraction as extraction

    source = tmp_path / "geometry.root"
    source.touch()
    monkeypatch.setattr(extraction.shutil, "which", lambda root: None)
    assert main(["ladder", str(source), "--node", LADDER]) == 1
    assert "ROOT executable not found" in capsys.readouterr().err


UNIT = "/TOP_1/sts_1/Unit04L_10"
CHILD_A = UNIT + "/Ladder_LadderType36_601"
CHILD_B = UNIT + "/Ladder_LadderType37_602"
OUTSIDE = UNIT + "0/Ladder_LadderType36_601"


def parent_rows():
    return [
        sensor(CHILD_B + "/Module100_3/Sensor04_0", center=(40, 50, 60)),
        sensor(CHILD_A + "/Module100_0/Sensor04_0"),
        sensor(CHILD_A + "/Module100_3/Sensor04_0"),
        sensor(OUTSIDE + "/Module100_0/Sensor04_0"),
    ]


@pytest.mark.parametrize(
    "node,expected",
    [
        (UNIT, (CHILD_A, CHILD_B)),
        (UNIT + "/", (CHILD_A, CHILD_B)),
        ("Unit04L_10", (CHILD_A, CHILD_B)),
        ("/TOP_1/sts_1", tuple(sorted((CHILD_A, CHILD_B, OUTSIDE)))),
        ("/", tuple(sorted((CHILD_A, CHILD_B, OUTSIDE)))),
        (CHILD_A, (CHILD_A,)),
    ],
)
def test_load_ladders_below_parent(tmp_path, node, expected):
    source = write_csv(tmp_path / "sensors.csv", parent_rows())
    ladders = load_ladder_geometries(source, node, frame="global")
    assert tuple(ladder.node_path for ladder in ladders) == expected
    first = next(ladder for ladder in ladders if ladder.node_path == CHILD_A)
    assert len(first.sensors) == 2
    assert first.sensors[0].center == (10, 20, 30)


def test_parent_selection_rejects_ambiguous_missing_and_nonancestor_nodes(tmp_path):
    source = write_csv(
        tmp_path / "sensors.csv",
        parent_rows()
        + [
            sensor("/OTHER_1/sts_1/Unit04L_10/LadderType0010_101/Module_0/Sensor01_0"),
        ],
    )
    with pytest.raises(ValueError, match="Ambiguous node"):
        load_ladder_geometries(source, "Unit04L_10")
    for node in ("", "Unit04L_1", "missing", CHILD_A + "/Module100_0"):
        with pytest.raises(ValueError, match="Node not found"):
            load_ladder_geometries(source, node)
    assert len(load_ladder_geometries(source, UNIT, frame="global")) == 2
    with pytest.raises(ValueError, match="Ladder not found"):
        load_ladder_geometry(source, UNIT)


@pytest.fixture
def fake_parent_extraction(monkeypatch):
    import geo_inspector.ladder as module

    calls = []

    def extract(geometry, output, root, *, stdout, node_transforms):
        calls.append((geometry, output, root))
        write_extraction(output, parent_rows(), node_transforms)

    monkeypatch.setattr(module, "extract_geometry", extract)
    return calls


def test_plural_extraction_runs_root_once(tmp_path, fake_parent_extraction):
    result = extract_ladder_geometries(
        tmp_path / "geometry.root", "Unit04L_10", root="configured-root"
    )
    assert tuple(ladder.node_path for ladder in result) == (CHILD_A, CHILD_B)
    assert len(fake_parent_extraction) == 1
    assert fake_parent_extraction[0][2] == "configured-root"
    assert not fake_parent_extraction[0][1].exists()


def test_parent_cli_writes_one_file_per_ladder(
    tmp_path, fake_parent_extraction, capsys
):
    source = tmp_path / "geometry.root"
    output = tmp_path / "results"
    assert (
        main(
            ["ladder", str(source), "--node", "Unit04L_10", "--output-dir", str(output)]
        )
        == 0
    )
    files = sorted(output.glob("*.json"))
    assert [path.name for path in files] == [
        "Ladder_LadderType36_601.json",
        "Ladder_LadderType37_602.json",
    ]
    first, second = [json.loads(path.read_text()) for path in files]
    assert first["node_path"] == CHILD_A
    assert first["sensor_count"] == 2
    assert second["node_path"] == CHILD_B
    assert second["sensor_count"] == 1
    assert second["sensors"][0]["center"] == [40, 50, 60]
    assert first["source_geometry"] == str(source.resolve())
    summary = json.loads(capsys.readouterr().out)
    assert summary["node_path"] == UNIT
    assert summary["ladder_count"] == 2
    assert summary["files"] == [str(path) for path in files]
    assert len(fake_parent_extraction) == 1


def test_higher_parent_export_preserves_hierarchy_without_collisions(
    tmp_path, fake_parent_extraction, capsys
):
    output = tmp_path / "results"
    assert (
        main(
            [
                "ladder",
                "geometry.root",
                "--node",
                "/TOP_1/sts_1",
                "--output-dir",
                str(output),
            ]
        )
        == 0
    )
    files = sorted(output.rglob("*.json"))
    assert len(files) == 3
    assert (output / "Unit04L_10/Ladder_LadderType36_601.json").is_file()
    assert (output / "Unit04L_100/Ladder_LadderType36_601.json").is_file()
    assert {json.loads(path.read_text())["node_path"] for path in files} == {
        CHILD_A,
        CHILD_B,
        OUTSIDE,
    }
    assert json.loads(capsys.readouterr().out)["ladder_count"] == 3


def test_single_ladder_can_use_output_directory(tmp_path, fake_parent_extraction):
    output = tmp_path / "results"
    assert (
        main(
            ["ladder", "geometry.root", "--node", CHILD_A, "--output-dir", str(output)]
        )
        == 0
    )
    files = list(output.glob("*.json"))
    assert len(files) == 1
    assert json.loads(files[0].read_text())["node_path"] == CHILD_A


@pytest.mark.parametrize("file_option", [[], ["--output", "existing.json"]])
def test_parent_requires_output_directory_even_with_one_ladder(
    tmp_path, fake_extraction, monkeypatch, capsys, file_option
):
    monkeypatch.chdir(tmp_path)
    output = tmp_path / "existing.json"
    output.write_text("preserve this")
    assert main(["ladder", "geometry.root", "--node", "Unit00R_1", *file_option]) == 1
    assert "Parent nodes require --output-dir" in capsys.readouterr().err
    assert output.read_text() == "preserve this"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["existing.json"]


def test_bulk_export_protects_geometry_input_before_writing(
    tmp_path, fake_parent_extraction, capsys
):
    # Protect even the second planned destination, before creating the first.
    source = tmp_path / "Ladder_LadderType37_602.json"
    source.write_bytes(b"geometry input")
    assert (
        main(["ladder", str(source), "--node", UNIT, "--output-dir", str(tmp_path)])
        == 1
    )
    assert "Output must differ" in capsys.readouterr().err
    assert source.read_bytes() == b"geometry input"
    assert not (tmp_path / "Ladder_LadderType36_601.json").exists()


def test_bulk_export_validates_all_ladders_before_writing(
    tmp_path, monkeypatch, capsys
):
    import geo_inspector.ladder as module

    def extract(geometry, output, root, *, stdout, node_transforms):
        rows = parent_rows()
        rows[0]["dx"] = -1
        write_extraction(output, rows, node_transforms)

    monkeypatch.setattr(module, "extract_geometry", extract)
    output = tmp_path / "results"
    assert (
        main(["ladder", "geometry.root", "--node", UNIT, "--output-dir", str(output)])
        == 1
    )
    assert "non-positive" in capsys.readouterr().err
    assert not output.exists()


def test_output_directory_is_relative_to_working_directory(
    tmp_path, fake_parent_extraction, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    assert (
        main(["ladder", "geometry.root", "--node", UNIT, "--output-dir", "results"])
        == 0
    )
    assert len(list((tmp_path / "results").glob("*.json"))) == 2
    assert not (tmp_path / "data").exists()


@pytest.mark.parametrize(
    "options",
    [
        ["--list", "--output-dir", "results"],
        ["--node", UNIT, "--output", "ladder.json", "--output-dir", "results"],
    ],
)
def test_invalid_export_options_fail_before_extraction(fake_parent_extraction, options):
    with pytest.raises(SystemExit) as error:
        main(["ladder", "geometry.root", *options])
    assert error.value.code == 2
    assert not fake_parent_extraction
