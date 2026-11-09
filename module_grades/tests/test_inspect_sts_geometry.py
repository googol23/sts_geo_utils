"""Run with python3 -m pytest module_grades/tests/test_inspect_sts_geometry.py."""
import csv
from pathlib import Path
import re

import pytest

from module_grades.inspect_sts_geometry import (
    join_sensors, main, parse_sensor_path, read_grades, ROTATION_FIELDS,
)

HERE = Path(__file__).resolve().parents[1]
PATH = '/TOP_1/sts_v22d_1/Unit00R_1/LadderType0010_101/HalfLadder10t_1/HalfLadder10t_Module01_1/Sensor01_1'


def write_csv(path, rows):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def sensor(path=PATH, size=2.2):
    return dict(node_path=path, x=-20, y=5, z=30, dx=6.2, dy=size, dz=0.03,
                **dict(zip(ROTATION_FIELDS, (1, 0, 0, 0, 1, 0, 0, 0, 1))))


def test_geometry_ladder_index_preserves_grade_lookup(tmp_path):
    path = tmp_path / 'sensors.csv'
    prefix = ('/top_1/sts_v22d_1/Unit00L_2/LadderType0101_105/'
              'HalfLadder01b_2/HalfLadder01b_Module')
    rows = [sensor(f'{prefix}{kind:02}_{index + 1}/Sensor{kind:02}_1', size)
            for index, (kind, size) in enumerate(((1, 2.2), (2, 4.2), (3, 6.2), (3, 6.2)))]
    write_csv(path, rows)
    grades = {(0, 'L', 0, 'B', index): (size, grade)
              for index, (size, grade) in enumerate(((2.2, 'C'), (4.2, 'C'), (6.2, 'B'), (6.2, 'B')))}
    joined = join_sensors(path, grades)
    assert [row['module_name'] for row in joined] == [f'M0DL5B{i}' for i in range(4)]
    assert [row['ladder'] for row in joined] == [0] * 4
    assert [row['grade'] for row in joined] == ['C', 'C', 'B', 'B']


def source_rows():
    """Use captured v22d paths and independently supplied sensor sizes.

    Positions remain synthetic; the ROOT integration test checks transforms.
    The capture was formerly stored in the unlabelled geo_inspector/cat file.
    """
    capture = (HERE / "tests/fixtures/v22d_module_table.txt").read_text()
    info = (HERE / "data/input/sts_v22d.geo.info").read_text()
    sizes = {name: float(size) for name, size in re.findall(
        r"^(Sensor[0-9]+): size\s+[0-9.]+ x\s+([0-9.]+)", info, re.MULTILINE
    )}
    paths = re.findall(r"/[^\s]+/Sensor[0-9]+_[0-9]+", capture)
    assert len(paths) == 876
    for path in paths:
        name = path.rsplit("/", 1)[1].rsplit("_", 1)[0]
        yield sensor(path, sizes[name])


def test_entire_supplied_grade_table(tmp_path):
    path = tmp_path / 'sensors.csv'
    rows = list(source_rows())
    write_csv(path, rows)
    grades = read_grades(HERE / 'data/input/uli_new_grades.txt')
    joined = join_sensors(path, grades, include_path=True)
    assert len(joined) == len(grades) == len(rows)
    assert len({row['module_name'] for row in joined}) == len(rows)
    assert {row['grade'] for row in joined} == set('ABCD')
    assert all(row['node_path'].endswith('_1') for row in joined)
    print(f'Validated {len(rows)} sensor/module mappings against supplied grades')


@pytest.mark.parametrize('change,error', [
    ({'x': float('nan')}, 'Nonfinite'),
    ({'dz': -1}, 'Nonpositive'),
    ({'node_path': PATH.replace('Unit00R', 'Unit02R')}, 'disagree'),
])
def test_reject_invalid_sensor(tmp_path, change, error):
    row = sensor()
    row.update(change)
    path = tmp_path / 'sensors.csv'
    write_csv(path, [row])
    with pytest.raises(ValueError, match=error):
        join_sensors(path, {(0, 'R', 3, 'T', 0): (2.2, 'C')})


def test_duplicate_and_missing(tmp_path):
    path = tmp_path / 'sensors.csv'
    grades = {(0, 'R', 3, 'T', 0): (2.2, 'C')}
    write_csv(path, [sensor(), sensor()])
    with pytest.raises(ValueError, match='Duplicate module key'):
        join_sensors(path, grades)
    write_csv(path, [sensor()])
    with pytest.raises(ValueError, match='No grade'):
        join_sensors(path, {})
    grades[(0, 'R', 3, 'B', 0)] = (2.2, 'B')
    with pytest.raises(ValueError, match='no sensor'):
        join_sensors(path, grades)


def test_cli_and_preserve_output_on_failure(tmp_path):
    path = tmp_path / 'sensors.csv'
    output = tmp_path / 'nested' / 'output' / 'joined.csv'
    write_csv(path, list(source_rows()))
    assert main(['--sensor-csv', str(path), '--output', str(output), '--include-path']) == 0
    previous = output.read_bytes()
    write_csv(path, [sensor()])
    assert main(['--sensor-csv', str(path), '--output', str(output)]) == 1
    assert output.read_bytes() == previous


@pytest.mark.parametrize('arguments,filename', [
    ([], 'module_geometry_grades.csv'),
    (['--output', 'custom.csv'], 'custom.csv'),
])
def test_output_directory_from_other_working_directory(tmp_path, monkeypatch, arguments, filename):
    import module_grades.inspect_sts_geometry as inspector

    output_dir = tmp_path / 'subproject' / 'data' / 'output'
    monkeypatch.setattr(inspector, 'OUTPUT_DIR', output_dir)
    monkeypatch.chdir(tmp_path)
    source = tmp_path / 'sensors.csv'
    write_csv(source, list(source_rows()))
    assert main(['--sensor-csv', str(source), *arguments]) == 0
    assert (output_dir / filename).is_file()
    assert not (tmp_path / filename).exists()


def test_duplicate_grades(tmp_path):
    path = tmp_path / 'grades.txt'
    path.write_text('station(unit) l/r ladder t/b module size grade\n' + '0 R 3 T 0 2.2 C\n' * 2)
    with pytest.raises(ValueError, match='Duplicate grade'):
        read_grades(path)


def test_size_mismatch_warns_and_preserves_geometry(tmp_path, capsys):
    path = tmp_path / "sensors.csv"
    write_csv(path, [sensor(size=4.2)])
    rows = join_sensors(path, {(0, "R", 3, "T", 0): (2.2, "C")})
    assert rows[0]["dy"] == 4.2
    assert "Sensor size mismatch" in capsys.readouterr().err
