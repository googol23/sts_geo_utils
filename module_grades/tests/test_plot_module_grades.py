import csv

import pytest

from module_grades.plot_module_grades import load_stations, projected_corners


def test_projected_sensor_corners():
    row = dict(x=10, y=20, dx=6, dy=2, r00=1, r01=0, r10=0, r11=1)
    assert projected_corners(row) == [(7, 19), (13, 19), (13, 21), (7, 21)]
    row.update(r00=0, r01=-1, r10=1, r11=0)
    assert projected_corners(row) == [(11, 17), (11, 23), (9, 23), (9, 17)]
    row.update(r00=-1, r01=0, r10=0, r11=1)
    assert projected_corners(row) == [(13, 19), (7, 19), (7, 21), (13, 21)]


def write_table(path, change=None):
    rows = [dict(module_name=f'M{s}DL5B0', station=s, grade='A',
                 x=10, y=20, dx=6, dy=2, r00=1, r01=0, r10=0, r11=1)
            for s in range(8)]
    if change:
        rows[0].update(change)
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def test_load_all_stations(tmp_path):
    path = tmp_path / 'modules.csv'
    write_table(path)
    stations = load_stations(path)
    assert list(stations) == list(range(8))
    assert all(len(rows) == 1 for rows in stations.values())


@pytest.mark.parametrize('change,message', [
    ({'grade': 'unknown'}, 'GRADE_PALETTE'),
    ({'dx': 0}, 'positive'),
    ({'x': 'nan'}, 'finite'),
    ({'station': 8}, '0–7'),
    ({'station': 1}, 'No modules for stations'),
])
def test_invalid_table(tmp_path, change, message):
    path = tmp_path / 'modules.csv'
    write_table(path, change)
    with pytest.raises(ValueError, match=message):
        load_stations(path)
