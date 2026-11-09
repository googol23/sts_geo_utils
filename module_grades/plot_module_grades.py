#!/usr/bin/env python3
"""Draw grade-coloured XY sensor projections from the module CSV.

Outputs:
  - One PNG per station: station_0_xy.png ... station_7_xy.png
  - One combined 4x2 canvas: all_stations_xy.png

All station plots use the same X/Y limits and equal axis scaling so that
station sizes and module positions can be compared directly.
"""

import argparse
import csv
import math
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.collections import PatchCollection
from matplotlib.patches import Patch, Polygon

if __package__:
    from .paths import OUTPUT_DIR
else:
    from paths import OUTPUT_DIR
DEFAULT_SOURCE = OUTPUT_DIR / "module_geometry_grades.csv"
DEFAULT_DPI = 300

GRADE_PALETTE = {
    "A": "#4daf4a",
    "B": "#377eb8",
    "C": "#ffbf00",
    "D": "#e41a1c",
}


def projected_corners(row):
    """Return the four XY corners of a projected sensor."""
    corners = []

    for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        local_x = sx * row["dx"] / 2
        local_y = sy * row["dy"] / 2

        corners.append(
            (
                row["x"] + row["r00"] * local_x + row["r01"] * local_y,
                row["y"] + row["r10"] * local_x + row["r11"] * local_y,
            )
        )

    return corners


def load_stations(source):
    """Load and validate module geometry grouped by station."""
    numeric = (
        "x",
        "y",
        "dx",
        "dy",
        "r00",
        "r01",
        "r10",
        "r11",
    )

    required = {
        "station",
        "grade",
        "module_name",
        *numeric,
    }

    stations = {station: [] for station in range(8)}

    with Path(source).open(newline="") as stream:
        reader = csv.DictReader(stream)

        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing CSV columns: {', '.join(sorted(missing))}")

        for line, raw in enumerate(reader, 2):
            try:
                station = int(raw["station"])

                row = {field: float(raw[field]) for field in numeric}

                grade = raw["grade"]

                if station not in stations:
                    raise ValueError("station must be in 0–7")

                if grade not in GRADE_PALETTE:
                    raise ValueError(f"grade {grade!r} is not in GRADE_PALETTE")

                if not all(math.isfinite(value) for value in row.values()):
                    raise ValueError("geometry values must be finite")

                if row["dx"] <= 0 or row["dy"] <= 0:
                    raise ValueError("sensor dimensions must be positive")

            except (ValueError, TypeError) as error:
                raise ValueError(f"CSV line {line}: {error}") from error

            row.update(
                grade=grade,
                module_name=raw["module_name"],
            )

            stations[station].append(row)

    empty = [station for station, rows in stations.items() if not rows]

    if empty:
        raise ValueError(
            f"No modules for stations: {empty}; expected all eight stations"
        )

    return stations


def common_extents(stations):
    """Calculate common symmetric X/Y limits for all stations."""
    corners = [
        point
        for rows in stations.values()
        for row in rows
        for point in projected_corners(row)
    ]

    if not corners:
        raise ValueError("No sensor geometry available for plotting")

    x_extent = max(abs(x) for x, _ in corners) * 1.06
    y_extent = max(abs(y) for _, y in corners) * 1.06

    return x_extent, y_extent


def grade_legend_handles():
    """Return legend handles shared by individual and combined plots."""
    return [
        Patch(
            facecolor=color,
            edgecolor="#303030",
            label=grade,
        )
        for grade, color in GRADE_PALETTE.items()
    ]


def draw_station(
    ax,
    station,
    rows,
    x_extent,
    y_extent,
    *,
    show_axis_labels=True,
):
    """Draw one station on an existing matplotlib Axes."""
    rectangles = [
        Polygon(
            projected_corners(row),
            closed=True,
        )
        for row in rows
    ]

    collection = PatchCollection(
        rectangles,
        facecolors=[GRADE_PALETTE[row["grade"]] for row in rows],
        edgecolors="#303030",
        linewidths=0.5,
    )

    ax.add_collection(collection)

    ax.set_xlim(-x_extent, x_extent)
    ax.set_ylim(-y_extent, y_extent)

    ax.set_aspect(
        "equal",
        adjustable="box",
    )

    ax.set_title(f"Station {station} ({len(rows)} modules)")

    if show_axis_labels:
        ax.set_xlabel("x [cm]")
        ax.set_ylabel("y [cm]")

    ax.set_axisbelow(True)

    ax.grid(
        True,
        color="#dddddd",
        linewidth=0.5,
    )

    ax.axhline(
        0,
        color="#777777",
        linewidth=0.6,
        zorder=0,
    )

    ax.axvline(
        0,
        color="#777777",
        linewidth=0.6,
        zorder=0,
    )


def plot_stations(stations, output_dir, dpi=DEFAULT_DPI):
    """Save eight individual station PNGs with common limits."""
    if dpi <= 0:
        raise ValueError("DPI must be positive")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    x_extent, y_extent = common_extents(stations)

    paths = []

    for station, rows in sorted(stations.items()):
        fig, ax = plt.subplots(
            figsize=(10, 10),
            constrained_layout=True,
        )

        try:
            draw_station(
                ax,
                station,
                rows,
                x_extent,
                y_extent,
            )

            ax.set_title(
                f"Station {station} — XY module projection ({len(rows)} modules)"
            )

            ax.legend(
                handles=grade_legend_handles(),
                title="Grade",
                loc="upper right",
            )

            path = output_dir / f"station_{station}_xy.png"

            fig.savefig(
                path,
                dpi=dpi,
                facecolor="white",
            )

            paths.append(path)

        finally:
            plt.close(fig)

    return paths


def plot_station_grid(stations, output_dir, dpi=DEFAULT_DPI):
    """Save all eight stations in one 4x2 canvas.

    The combined plot uses:
      - 4 columns x 2 rows
      - identical X/Y limits for every station
      - equal X/Y aspect ratio
      - one common grade legend
    """
    if dpi <= 0:
        raise ValueError("DPI must be positive")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    x_extent, y_extent = common_extents(stations)

    fig, axes = plt.subplots(
        nrows=2,
        ncols=4,
        figsize=(20, 11),
        sharex=True,
        sharey=True,
    )

    try:
        flat_axes = axes.flat

        for station, ax in enumerate(flat_axes):
            rows = stations[station]

            draw_station(
                ax,
                station,
                rows,
                x_extent,
                y_extent,
                show_axis_labels=False,
            )

            # Only the bottom row needs X labels.
            if station >= 4:
                ax.set_xlabel("x [cm]")

            # Only the left column needs Y labels.
            if station % 4 == 0:
                ax.set_ylabel("y [cm]")

        fig.suptitle(
            "STS module grades — XY station projections",
            fontsize=16,
        )

        # One legend for the complete 4x2 canvas.
        fig.legend(
            handles=grade_legend_handles(),
            title="Grade",
            loc="lower center",
            ncol=len(GRADE_PALETTE),
            bbox_to_anchor=(0.5, 0.015),
            frameon=True,
        )

        # Explicit spacing leaves room for the common legend and title.
        fig.subplots_adjust(
            left=0.06,
            right=0.985,
            bottom=0.10,
            top=0.91,
            wspace=0.15,
            hspace=0.18,
        )

        path = output_dir / "all_stations_xy.png"

        fig.savefig(
            path,
            dpi=dpi,
            facecolor="white",
        )

        return path

    finally:
        plt.close(fig)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "source",
        nargs="?",
        type=Path,
        default=DEFAULT_SOURCE,
    )

    parser.add_argument(
        "--dpi",
        type=int,
        default=DEFAULT_DPI,
        help=f"PNG resolution (default: {DEFAULT_DPI})",
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("."),
        help="Output directory; relative paths resolve under ./data/output",
    )

    args = parser.parse_args(argv)

    if args.dpi <= 0:
        parser.error("--dpi must be positive")

    if not args.output_dir.is_absolute():
        args.output_dir = OUTPUT_DIR / args.output_dir

    try:
        stations = load_stations(args.source)

        # Existing individual station plots.
        for path in plot_stations(
            stations,
            args.output_dir,
            args.dpi,
        ):
            print(f"Saved {path}")

        # New combined 4x2 station canvas.
        combined_path = plot_station_grid(
            stations,
            args.output_dir,
            args.dpi,
        )

        print(f"Saved {combined_path}")

    except (OSError, ValueError) as error:
        print(
            f"plot_module_grades: {error}",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
