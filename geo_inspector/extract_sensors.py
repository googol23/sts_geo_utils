#!/usr/bin/env python3
"""Extract STS sensor positions and axis-aligned sizes from a ROOT geometry."""

import argparse
import csv
import sys
from array import array
from contextlib import nullcontext

if __package__:
    from .geometry import find_node, list_nodes, open_geometry
else:
    from geometry import find_node, list_nodes, open_geometry


def local_bounds(shape):
    """Return a shape's local bounding-box bounds as (min, max) 3-tuples."""
    shape.ComputeBBox()
    box = shape
    if not all(
        hasattr(box, method) for method in ("GetOrigin", "GetDX", "GetDY", "GetDZ")
    ):
        get_fitting_box = getattr(shape, "GetFittingBox", None)
        box = get_fitting_box() if get_fitting_box else None
    if not box or not all(
        hasattr(box, method) for method in ("GetOrigin", "GetDX", "GetDY", "GetDZ")
    ):
        raise RuntimeError(f"could not get bounding box for {shape.GetName()}")
    origin = box.GetOrigin()
    half_sizes = (box.GetDX(), box.GetDY(), box.GetDZ())
    return (
        tuple(float(origin[i]) - half_sizes[i] for i in range(3)),
        tuple(float(origin[i]) + half_sizes[i] for i in range(3)),
    )


def sensor_rows(geometry, node_path=None):
    """Yield sensor path and global center/dimensions in ROOT geometry units."""
    top = geometry.GetTopNode()
    if node_path is not None and find_node(top, node_path) is None:
        raise ValueError(f"geometry node not found: {node_path}")
    prefix = None
    if node_path is not None:
        names = tuple(part for part in node_path.split("/") if part)
        if names and names[0] != top.GetName():
            names = (top.GetName(),) + names
        prefix = "/" + "/".join(names)

    navigator = geometry.GetCurrentNavigator()
    for path, node in list_nodes(top):
        if prefix is not None and path != prefix and not path.startswith(prefix + "/"):
            continue
        volume = node.GetVolume()
        shape = volume.GetShape()
        names = (node.GetName(), volume.GetName(), shape.GetName() if shape else "")
        if shape is None or not any("sensor" in name.lower() for name in names):
            continue
        if not navigator.cd(path):
            raise RuntimeError(f"could not navigate to geometry node: {path}")

        minimum, maximum = local_bounds(shape)
        matrix = navigator.GetCurrentMatrix()
        corners = []
        for x in (minimum[0], maximum[0]):
            for y in (minimum[1], maximum[1]):
                for z in (minimum[2], maximum[2]):
                    local = array("d", (x, y, z))
                    master = array("d", (0.0, 0.0, 0.0))
                    matrix.LocalToMaster(local, master)
                    corners.append(tuple(master))

        global_min = tuple(min(point[i] for point in corners) for i in range(3))
        global_max = tuple(max(point[i] for point in corners) for i in range(3))
        center = tuple((global_min[i] + global_max[i]) / 2.0 for i in range(3))
        size = tuple(global_max[i] - global_min[i] for i in range(3))
        yield path, center + size


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("geometry", help="input ROOT geometry file")
    parser.add_argument(
        "--node", help="optional starting node path; defaults to the whole geometry"
    )
    parser.add_argument(
        "-o", "--output", help="CSV output file; defaults to standard output"
    )
    args = parser.parse_args(argv)

    output_context = (
        open(args.output, "w", newline="", encoding="utf-8")
        if args.output
        else nullcontext(sys.stdout)
    )
    with output_context as output:
        writer = csv.writer(output)
        writer.writerow(("sensor", "x", "y", "z", "dx", "dy", "dz"))
        root_file, geometry = open_geometry(args.geometry)
        try:
            for path, values in sensor_rows(geometry, args.node):
                writer.writerow((path, *(f"{value:.9g}" for value in values)))
        finally:
            root_file.Close()


if __name__ == "__main__":
    main()
