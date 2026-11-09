#!/usr/bin/env python3
"""Extract STS sensor placements with external ROOT and join module grades."""

import argparse
import csv
import math
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from geo_inspector.extraction import extract_geometry
from geo_inspector.sts import NUMERIC_FIELDS, ROTATION_FIELDS, STATION_WIDTHS, parse_sensor_path

if __package__:
    from .paths import INPUT_DIR, OUTPUT_DIR
else:
    from paths import INPUT_DIR, OUTPUT_DIR


# ---------------------------------------------------------------------------
# Grade table
# ---------------------------------------------------------------------------

def read_grades(path):
    grades = {}

    with Path(path).open() as stream:
        header = next(stream, '').split()

        expected_header = [
            'station(unit)',
            'l/r',
            'ladder',
            't/b',
            'module',
            'size',
            'grade',
        ]

        if header != expected_header:
            raise ValueError(
                'Unexpected grade table header'
            )

        for line_number, line in enumerate(stream, 2):
            if not line.strip():
                continue

            fields = line.split()

            if len(fields) != 7:
                raise ValueError(
                    f'Grade line {line_number}: '
                    f'expected seven columns'
                )

            (
                station,
                side,
                ladder,
                half,
                module,
                size,
                grade,
            ) = fields

            key = (
                int(station),
                side,
                int(ladder),
                half,
                int(module),
            )

            size = float(size)

            if (
                not 0 <= key[0] < len(STATION_WIDTHS)
                or side not in ('L', 'R')
                or not 0 <= key[2] < STATION_WIDTHS[key[0]] // 2
                or half not in ('T', 'B')
                or not 0 <= key[4] <= 9
                or not math.isfinite(size)
                or size <= 0
                or not grade
            ):
                raise ValueError(
                    f'Invalid grade line {line_number}: '
                    f'{line.strip()}'
                )

            if key in grades:
                raise ValueError(
                    f'Duplicate grade key at line '
                    f'{line_number}: {key}'
                )

            grades[key] = (
                size,
                grade,
            )

    if not grades:
        raise ValueError(
            'Grade table is empty'
        )

    return grades


# ---------------------------------------------------------------------------
# Join geometry and grade information
# ---------------------------------------------------------------------------

def join_sensors(
    sensor_csv,
    grades,
    naming_version='STS3_5',
    include_path=False,
):
    result = []
    seen = set()
    size_mismatch_count = 0

    with Path(sensor_csv).open(newline='') as stream:
        reader = csv.DictReader(stream)

        required = {
            'node_path',
            *NUMERIC_FIELDS,
            *ROTATION_FIELDS,
        }

        if not required.issubset(reader.fieldnames or []):
            raise ValueError(
                f'Sensor CSV requires columns: '
                f'{sorted(required)}'
            )

        for raw in reader:
            path = raw['node_path']

            key, name, sensor = parse_sensor_path(
                path,
                naming_version,
            )

            # Both supported generators have one physical sensor per module.
            if sensor != 0:
                raise ValueError(
                    f'Expected one sensor per module: {path}'
                )

            if key in seen:
                raise ValueError(
                    f'Duplicate module key {key}: {path}'
                )

            seen.add(key)

            if key not in grades:
                raise ValueError(
                    f'No grade for module {name}, '
                    f'table key {key}: {path}'
                )

            numbers = {
                field: float(raw[field])
                for field in (
                    *NUMERIC_FIELDS,
                    *ROTATION_FIELDS,
                )
            }

            if not all(
                math.isfinite(value)
                for value in numbers.values()
            ):
                raise ValueError(
                    f'Nonfinite geometry values: {path}'
                )

            if any(
                numbers[field] <= 0
                for field in ('dx', 'dy', 'dz')
            ):
                raise ValueError(
                    f'Nonpositive sensor dimensions: {path}'
                )

            grade_size, grade = grades[key]

            # --------------------------------------------------------------
            # Sensor-size consistency check
            #
            # The ROOT geometry is authoritative.
            #
            # A discrepancy in the grade table is reported to the user but
            # does NOT prevent output generation.
            # --------------------------------------------------------------

            if not math.isclose(
                numbers['dy'],
                grade_size,
                rel_tol=0,
                abs_tol=1e-6,
            ):
                size_mismatch_count += 1

                print(
                    f'WARNING: Sensor size mismatch for {name}: '
                    f'geometry {numbers["dy"]}, '
                    f'grade table {grade_size}; '
                    f'using geometry value',
                    file=sys.stderr,
                )

            row = dict(
                module_name=name,
                station=key[0],
                side=key[1],
                ladder=key[2],
                half=key[3],
                module=key[4],
                grade=grade,
                **numbers,
            )

            if include_path:
                row['node_path'] = path

            result.append(row)

    missing = grades.keys() - seen

    if missing:
        raise ValueError(
            f'{len(missing)} grade entries have no sensor; '
            f'examples: {sorted(missing)[:5]}'
        )

    if not result:
        raise ValueError(
            'No sensors were found'
        )

    if size_mismatch_count:
        print(
            f'WARNING: {size_mismatch_count} sensor size mismatch(es) '
            f'were found; ROOT geometry dimensions were used.',
            file=sys.stderr,
        )

    return sorted(
        result,
        key=lambda row: (
            row['station'],
            row['side'],
            row['ladder'],
            row['half'],
            row['module'],
        ),
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__,
    )

    inputs = parser.add_mutually_exclusive_group(
        required=True,
    )

    inputs.add_argument(
        '--geometry',
        type=Path,
        help='ROOT geometry file',
    )

    inputs.add_argument(
        '--sensor-csv',
        type=Path,
        help='CSV already produced by the ROOT macro',
    )

    parser.add_argument(
        '--grades',
        type=Path,
        default=INPUT_DIR / 'uli_new_grades.txt',
    )

    parser.add_argument(
        '--output',
        type=Path,
        default=Path('module_geometry_grades.csv'),
        help=(
            'Output filename relative to '
            './data/output, '
            'or an absolute path'
        ),
    )

    parser.add_argument(
        '--naming-version',
        choices=('STS8', 'STS3_5'),
        default='STS3_5',
    )

    parser.add_argument(
        '--include-path',
        action='store_true',
    )

    parser.add_argument(
        '--root',
        default='root',
        help=(
            'ROOT executable from your external environment'
        ),
    )

    args = parser.parse_args(argv)

    if not args.output.is_absolute():
        args.output = OUTPUT_DIR / args.output

    try:
        # ------------------------------------------------------------------
        # Validate inputs
        # ------------------------------------------------------------------

        for source in (
            args.geometry,
            args.sensor_csv,
            args.grades,
        ):
            if (
                source
                and source.resolve() == args.output.resolve()
            ):
                raise ValueError(
                    'Output must differ from all input files'
                )

        grades = read_grades(
            args.grades
        )

        # ------------------------------------------------------------------
        # Extract geometry
        # ------------------------------------------------------------------

        with tempfile.TemporaryDirectory(
            prefix='sts-inspector-'
        ) as directory:

            sensor_csv = args.sensor_csv

            if args.geometry:
                sensor_csv = Path(directory) / 'sensors.csv'
                extract_geometry(args.geometry, sensor_csv, args.root)

            # ----------------------------------------------------------------
            # Join geometry and grade data
            # ----------------------------------------------------------------

            rows = join_sensors(
                sensor_csv,
                grades,
                args.naming_version,
                args.include_path,
            )

        # ------------------------------------------------------------------
        # Write output atomically
        # ------------------------------------------------------------------

        args.output.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with tempfile.NamedTemporaryFile(
            mode='w',
            newline='',
            dir=args.output.resolve().parent,
            delete=False,
        ) as stream:

            temporary = Path(
                stream.name
            )

            try:
                writer = csv.DictWriter(
                    stream,
                    fieldnames=list(rows[0]),
                )

                writer.writeheader()
                writer.writerows(rows)

                stream.close()

                temporary.replace(
                    args.output
                )

            finally:
                temporary.unlink(
                    missing_ok=True
                )

        print(
            f'Wrote {len(rows)} modules to '
            f'{args.output} '
            f'(cm, full sensor dimensions)'
        )

        return 0

    except (
        OSError,
        ValueError,
        subprocess.CalledProcessError,
    ) as error:

        print(
            f'inspect_sts_geometry: {error}',
            file=sys.stderr,
        )

        return 1


if __name__ == '__main__':
    sys.exit(main())
