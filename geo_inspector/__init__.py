"""Standalone ROOT geometry inspection without rendering or grade dependencies.

PyROOT is imported only when open_geometry is called. External ROOT extraction
runs the configured root executable instead of importing PyROOT.
"""

from .extract_sensors import local_bounds, sensor_rows
from .extraction import extract_geometry
from .geometry import children, find_node, list_nodes, open_geometry
from .ladder import (
    BoundingBox,
    LadderGeometry,
    NodeFrame,
    SensorGeometry,
    available_ladders,
    extract_ladder_geometries,
    extract_ladder_geometry,
    load_ladder_geometries,
    load_ladder_geometry,
)
from .sts import parse_sensor_path

__version__ = "0.1.0"
__all__ = [
    "children",
    "find_node",
    "list_nodes",
    "open_geometry",
    "local_bounds",
    "sensor_rows",
    "extract_geometry",
    "parse_sensor_path",
    "BoundingBox",
    "SensorGeometry",
    "LadderGeometry",
    "NodeFrame",
    "available_ladders",
    "load_ladder_geometry",
    "extract_ladder_geometry",
    "load_ladder_geometries",
    "extract_ladder_geometries",
]
