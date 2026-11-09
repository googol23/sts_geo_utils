#!/usr/bin/env python3
"""Load the complete module CSV and print selected columns."""

import argparse
from pathlib import Path
import sys

import pandas as pd

if __package__:
    from .paths import OUTPUT_DIR
else:
    from paths import OUTPUT_DIR


# Edit this list to choose the displayed columns and their order.
PRINT_COLUMNS = [
    "module_name",
    # "x",
    # "y",
    # "z",
    # "dx",
    # "dy",
    # "dz",
    # "grade",
    "node_path",
]
PRINT_ROWS = 10


def load_table(source: str | Path) -> pd.DataFrame:
    """Read every column, using the source file's first line as the header."""
    return pd.read_csv(source, header=0)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "source",
        nargs="?",
        type=Path,
        default=OUTPUT_DIR / "module_geometry_grades.csv",
        help="Module CSV (default: ./data/output/module_geometry_grades.csv)",
    )
    parser.add_argument(
        "--rows",
        type=int,
        default=PRINT_ROWS,
        help=f"Maximum number of rows to print (default: {PRINT_ROWS})",
    )
    args = parser.parse_args(argv)
    if args.rows < 0:
        parser.error("--rows must be zero or greater")
    try:
        df = load_table(args.source)
        print(f"Available columns: {', '.join(df.columns)}")
        missing = [column for column in PRINT_COLUMNS if column not in df.columns]
        if missing:
            raise ValueError(f"Missing display columns: {', '.join(missing)}")
        preview = df.loc[:, PRINT_COLUMNS].head(args.rows)
        print(f"\nShowing {len(preview)} of {len(df)} rows:")
        print(preview.to_string(index=False))
    except (OSError, ValueError, pd.errors.ParserError) as error:
        print(f"inspect_module_table: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
