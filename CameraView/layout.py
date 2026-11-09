"""Matrix-based canvas layouts for camera-view panels."""

from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass(frozen=True)
class Pad:
    index: str
    x: int
    y: int
    width: int
    height: int


class PadLayout:
    """Partition a canvas using a rectangular matrix of pad identifiers.

    Every matrix cell has equal size. Repeated identifiers are merged into a
    single rectangular pad; identifiers may be strings (including aliases).
    """

    def __init__(self, matrix):
        rows = tuple(str(row) for row in matrix)
        if not rows or not rows[0] or any(len(row) != len(rows[0]) for row in rows):
            raise ValueError("layout matrix must be non-empty and rectangular")
        self.matrix = rows
        self.rows = len(rows)
        self.columns = len(rows[0])
        self._pads = {}
        for y, row in enumerate(rows):
            for x, identifier in enumerate(row):
                self._pads.setdefault(identifier, []).append((x, y))
        for identifier, cells in self._pads.items():
            xs = [cell[0] for cell in cells]
            ys = [cell[1] for cell in cells]
            x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
            if len(cells) != (x1 - x0 + 1) * (y1 - y0 + 1):
                raise ValueError("pad %r must form one rectangle" % identifier)

    @property
    def indices(self):
        return tuple(self._pads)

    def bounds(self, width, height):
        """Return {pad id: (x, y, width, height)} pixel rectangles."""
        if width <= 0 or height <= 0:
            raise ValueError("canvas dimensions must be positive")
        x_edges = [round(i * width / self.columns) for i in range(self.columns + 1)]
        y_edges = [round(i * height / self.rows) for i in range(self.rows + 1)]
        result = {}
        for identifier, cells in self._pads.items():
            xs = [cell[0] for cell in cells]
            ys = [cell[1] for cell in cells]
            x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
            result[identifier] = (
                x_edges[x0], y_edges[y0], x_edges[x1 + 1] - x_edges[x0],
                y_edges[y1 + 1] - y_edges[y0],
            )
        return result
