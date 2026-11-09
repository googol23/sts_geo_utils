#!/usr/bin/env python3
"""Four solid views of a ROOT TGeo support using CPU rasterization, with orthographic grids and calibrated axes.

Requires PyROOT, VTK (mesh containers only), NumPy and Pillow.
No X11, EGL, OSMesa, GPU or VTK render window is required.
"""

import argparse
import math
import os
import sys
from collections import defaultdict

DEFAULT_GEOMETRY = "/u/dramirez/cbm/CBMROOT_250323/src/geometry/sts/sts_v26a.geo.root"
DEFAULT_OUTPUT = "data/output/capture_sts_cfSupport.root"
PATH = ("Unit00R_1", "Ladder_LadderType09_101", "LadderType09_cfSupport_0")

# Layout: three stacked pads on the left, one full-height pad on the right.
LEFT_COLUMN_FRACTION = 0.7

# Image export and typography settings.
OUTPUT_DPI = 600  # PNG print-resolution metadata (dots per inch).
TICK_LABEL_FONT_SIZE = 20  # Pixel size of orthographic tick numbers.
PAD_TITLE_FONT_SIZE = 26  # Approximately twice the original default PIL font.
AXIS_TITLE_FONT_SIZE = 16  # Pixel size of X/Y/Z axis labels.
DIMENSION_FONT_SIZE = 18
DIMENSION_COLOR = (165, 45, 40)
DIMENSION_LINE_WIDTH = 2
DIMENSION_OFFSET_PX = 48
DIMENSION_EXTENSION_DASH_PX = (3, 5)
DIMENSION_EXTENSION_WIDTH = 2
DIMENSION_EXTENSION_OVERHANG_PX = 12
DIMENSION_ARROW_LENGTH_PX = 9
DIMENSION_ARROW_HALF_WIDTH_PX = 5

# All measurements are declared here; the drawing code is shared.
# Shapes are matched by ROOT TGeoShape name. 'instance' chooses a particular
# placed solid by its transformed bounding-box center in the given axis.
# 'all' merges every matching placement; 'topmost' selects the highest one.
# 'closest_to_center' selects the placement whose bounding-box center is
# nearest the local origin (0, 0, 0), optionally along 'center_axis'.
# Avoid 'all' for a single pillar center: merging pillars averages their extents.
# 'point' chooses a 3-D reference point: center, min_x, max_x, min_y,
# max_y, min_z or max_z. All geometry coordinates are in cm.
# 'axis' is the measured component; 'side' positions the dimension line.
DIMENSIONS = {
    "XOY": [
        {
            "name": "Apex pillar center to base pillar center",
            "axis": "Y",
            "side": "bottom",
            "offset_px": 400,
            "from": {
                "shape": "vert_pillar_shp",
                "instance": "topmost",
                "point": "center",
            },
            "to": {
                "shape": "vert_pillar_shp",
                "instance": "bottommost",
                "point": "center",
            },
        },
        {
            "name": "Left-to-right pillar centers",
            "axis": "X",
            "side": "right",
            "offset_px": DIMENSION_OFFSET_PX,
            "from": {
                "shape": "vert_pillar_shp",
                "instance": "leftmost",
                "point": "center",
            },
            "to": {
                "shape": "vert_pillar_shp",
                "instance": "rightmost",
                "point": "center",
            },
        },
    ],
    "ZOX": [
        {
            "name": "Segment base Z extent",
            "axis": "Z",
            "side": "bottom",
            "offset_px": 150,
            "from": {
                "shape": "segment_base_shp",
                "instance": "closest_to_center",
                "point": "max_z",
            },
            "to": {
                "shape": "segment_base_shp",
                "instance": "closest_to_center",
                "point": "min_z",
            },
        },
    ],
    "ZOY": [
        {
            "name": "Segment base Z extent",
            "axis": "Z",
            "side": "bottom",
            "offset_px": 90,
            "from": {
                "shape": "segment_sides_shape",
                "instance": "closest_to_center",
                "point": "max_z",
            },
            "to": {
                "shape": "segment_sides_shape",
                "instance": "closest_to_center",
                "point": "min_z",
            },
        },
    ],
}
ACTOR_SHAPE_NAMES = {}
ACTOR_NODE_PATHS = {}
ACTOR_INNER_RADII = {}

# Per-pad camera configuration. Coordinates are in the geometry's X/Y/Z frame.
# direction: vector from the object toward the camera (not necessarily unit length).
# up: preferred vertical direction on the image; corrected to be perpendicular
#     to the viewing direction automatically.
# zoom: image magnification relative to the original auto-fit (1.0 = unchanged).
# perspective: True = perspective, False = orthographic.
# Orthographic frames and dimension orientation follow the camera basis
# automatically for any axis-aligned direction/up combination.
CAMERA_VIEWS = {
    "Perspective": {
        "direction": (1, -1, 0.85),
        "up": (0, 1, 0),
        "zoom": 1.0,
        "perspective": True,
    },
    "XOY": {
        "direction": (0, 0, 1),
        "up": (1, 0, 0),
        "zoom": 1.0,
        "perspective": False,
    },
    "ZOX": {
        "direction": (0, 1, 0),
        "up": (1, 0, 0),
        "zoom": 2.0,
        "perspective": False,
    },
    "ZOY": {
        "direction": (1, 0, 0),
        "up": (0, 1, 0),
        "zoom": 2.0,
        "perspective": False,
    },
}


def load_font(size):
    """Load a scalable font; fall back to Pillow's bundled/default font."""
    from PIL import ImageFont

    for name in ("DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def children(volume):
    nodes = volume.GetNodes()
    if nodes:
        for i in range(nodes.GetEntriesFast()):
            node = nodes.At(i)
            if node:
                yield node


def find_support(node):
    if node.GetName() == PATH[0]:
        current = node
        for name in PATH[1:]:
            current = next(
                (n for n in children(current.GetVolume()) if n.GetName() == name), None
            )
            if current is None:
                break
        if current is not None:
            return current
    for child in children(node.GetVolume()):
        result = find_support(child)
        if result is not None:
            return result
    return None


def open_geometry(ROOT, filename):
    f = ROOT.TFile.Open(filename, "READ")
    if not f or f.IsZombie():
        raise RuntimeError("Cannot open ROOT file: " + filename)
    keys = list(f.GetListOfKeys())
    for key in keys:
        cls = ROOT.TClass.GetClass(key.GetClassName())
        if cls and cls.InheritsFrom(ROOT.TGeoManager.Class()):
            geo = key.ReadObj()
            ROOT.gGeoManager = geo
            return f, geo
    # The CBM file can contain a standalone TGeoVolumeAssembly.
    geo = ROOT.TGeoManager("capture_geometry", "STS capture geometry")
    for key in keys:
        cls = ROOT.TClass.GetClass(key.GetClassName())
        if cls and cls.InheritsFrom(ROOT.TGeoVolume.Class()):
            volume = key.ReadObj()
            seen = set()

            def register(v):
                address = ROOT.addressof(v)
                if address in seen:
                    return
                seen.add(address)
                geo.AddVolume(v)
                for n in children(v):
                    register(n.GetVolume())

            register(volume)
            geo.SetTopVolume(volume)
            geo.CloseGeometry()
            ROOT.gGeoManager = geo
            return f, geo
    raise RuntimeError("No TGeoManager or TGeoVolume found")


def matrix4(vtk, root_matrix):
    """Copy ROOT matrix elements in C++ before accessing from Python."""
    result = vtk.vtkMatrix4x4()
    result.Identity()
    if root_matrix:
        values = ROOT_MATRIX_BRIDGE(root_matrix)
        for i in range(3):
            for j in range(3):
                result.SetElement(i, j, values[4 * i + j])
            result.SetElement(i, 3, values[4 * i + 3])
    return result


ROOT_MATRIX_BRIDGE = None


def multiply(vtk, a, b):
    out = vtk.vtkMatrix4x4()
    vtk.vtkMatrix4x4.Multiply4x4(a, b, out)
    return out


def buffer_field(buf, method, legacy):
    """Support ROOT 6.30 PyROOT accessors and older data-member bindings."""
    member = getattr(buf, method, None)
    if member is not None:
        return member() if callable(member) else member
    member = getattr(buf, legacy, None)
    if member is not None:
        return member() if callable(member) else member
    raise AttributeError("TBuffer3D exposes neither %s() nor %s" % (method, legacy))


def install_root_buffer_bridge(ROOT):
    """Copy TBuffer3D arrays on the C++ side to avoid PyROOT char* conversions."""
    ok = ROOT.gInterpreter.Declare(r"""
    #include <TGeoMatrix.h>
    #include <TGeoShape.h>
    #include <TBuffer3D.h>
    #include <vector>
    namespace sts_bridge {
      std::vector<double> matrix_values(const TGeoMatrix* m) {
        std::vector<double> v(12, 0.0);
        if (!m) return v;
        const double* r = m->GetRotationMatrix();
        const double* t = m->GetTranslation();
        for (int i = 0; i < 3; ++i) {
          for (int j = 0; j < 3; ++j) v[4*i+j] = r[3*i+j];
          v[4*i+3] = t[i];
        }
        return v;
      }
      struct MeshBuffer {
        std::vector<double> points;
        std::vector<int> segments;
        std::vector<int> polygons;
      };
      MeshBuffer extract(TGeoShape* shape) {
        MeshBuffer result;
        if (!shape) return result;
        const TBuffer3D& b = shape->GetBuffer3D(TBuffer3D::kAll, true);
        if (b.NbPnts() && b.fPnts)
          result.points.assign(b.fPnts, b.fPnts + 3*b.NbPnts());
        if (b.NbSegs() && b.fSegs)
          result.segments.assign(b.fSegs, b.fSegs + 3*b.NbSegs());
        if (b.NbPols() && b.fPols) {
          // Polygon records are variable length: color, nSegments, segment IDs.
          const auto* p = b.fPols;
          unsigned offset = 0;
          for (unsigned i = 0; i < b.NbPols(); ++i) {
            const int count = p[offset+1];
            if (count < 0 || count > 1000000) break;
            for (int j = 0; j < count+2; ++j)
              result.polygons.push_back(p[offset+j]);
            offset += count+2;
          }
        }
        return result;
      }
    }
    """)
    if not ok:
        raise RuntimeError("C++ ROOT buffer bridge failed to compile")
    global ROOT_MATRIX_BRIDGE
    ROOT_MATRIX_BRIDGE = ROOT.sts_bridge.matrix_values


def shape_mesh(ROOT, vtk, shape):
    """Convert C++-copied ROOT polygon data into VTK surface cells."""
    buf = ROOT.sts_bridge.extract(shape)
    point_data, segment_data, polygon_data = buf.points, buf.segments, buf.polygons
    npts, nsegs = len(point_data) // 3, len(segment_data) // 3
    if not npts or not polygon_data:
        return None
    pts = vtk.vtkPoints()
    for i in range(npts):
        pts.InsertNextPoint(
            float(point_data[3 * i]),
            float(point_data[3 * i + 1]),
            float(point_data[3 * i + 2]),
        )
    segs = [
        (abs(int(segment_data[3 * i + 1])), abs(int(segment_data[3 * i + 2])))
        for i in range(nsegs)
    ]
    cells = vtk.vtkCellArray()
    offset = 0
    while offset + 2 <= len(polygon_data):
        count = int(polygon_data[offset + 1])
        if count < 0 or offset + count + 2 > len(polygon_data):
            break
        ids = [abs(int(polygon_data[offset + 2 + j])) for j in range(count)]
        offset += count + 2
        if count < 3:
            continue
        edges = [segs[i] for i in ids if i < nsegs]
        if len(edges) < 3:
            continue
        adjacency = defaultdict(list)
        for i, (a, b) in enumerate(edges):
            adjacency[a].append((b, i))
            adjacency[b].append((a, i))
        first = edges[0][0]
        perimeter, used = [first], set()
        cursor = first
        for _ in range(len(edges)):
            options = [(other, i) for other, i in adjacency[cursor] if i not in used]
            if not options:
                break
            nxt, edge_i = options[0]
            used.add(edge_i)
            if nxt == first:
                break
            perimeter.append(nxt)
            cursor = nxt
        if len(perimeter) < 3 or len(used) != len(edges):
            continue
        polygon = vtk.vtkPolygon()
        polygon.GetPointIds().SetNumberOfIds(len(perimeter))
        for j, p in enumerate(perimeter):
            polygon.GetPointIds().SetId(j, p)
        cells.InsertNextCell(polygon)
    if cells.GetNumberOfCells() == 0:
        return None
    poly = vtk.vtkPolyData()
    poly.SetPoints(pts)
    poly.SetPolys(cells)
    triangles = vtk.vtkTriangleFilter()
    triangles.SetInputData(poly)
    triangles.Update()
    out = vtk.vtkPolyData()
    out.ShallowCopy(triangles.GetOutput())
    return out if out.GetNumberOfPolys() else None


def normalize_node_paths(paths):
    """Normalize relative node paths for subtree selection."""
    if paths is None:
        return ()
    if isinstance(paths, (str, bytes)):
        raise ValueError("include_nodes must be a sequence of relative node paths")
    normalized = []
    for path in paths:
        parts = path.split("/") if isinstance(path, str) else tuple(path)
        parts = tuple(part for part in parts if part)
        if not parts or any(part in (".", "..") for part in parts):
            raise ValueError("include_nodes paths must identify relative nodes")
        normalized.append(parts)
    return tuple(normalized)


def node_path_is_included(path, include_nodes):
    """Return whether a node is at or below any selected relative path."""
    return not include_nodes or any(
        path[: len(selected)] == selected for selected in include_nodes
    )


def build_actors(ROOT, vtk, node, renderer, exclude_shapes=None, include_nodes=None):
    excluded_shapes = set(exclude_shapes or ())
    include_nodes = normalize_node_paths(include_nodes)
    found_nodes = set()
    cache = {}
    actors = []
    skipped = set()
    stats = defaultdict(int)
    identity = vtk.vtkMatrix4x4()
    identity.Identity()

    def visit(volume, transform, path):
        stats["volumes"] += 1
        if path in include_nodes:
            found_nodes.add(path)
        draw_volume = node_path_is_included(path, include_nodes)
        # An invisible container does not necessarily hide its daughters.
        shape = volume.GetShape()
        if (
            draw_volume
            and volume.IsVisible()
            and shape
            and not volume.IsAssembly()
            and shape.GetName() in excluded_shapes
        ):
            stats["excluded_solids"] += 1
        elif draw_volume and volume.IsVisible() and shape and not volume.IsAssembly():
            stats["candidate_solids"] += 1
            key = ROOT.addressof(shape)
            if key not in cache:
                try:
                    cache[key] = shape_mesh(ROOT, vtk, shape)
                except Exception as exc:
                    cache[key] = None
                    print(
                        "WARNING: failed to tessellate",
                        shape.GetName(),
                        str(exc),
                        file=sys.stderr,
                    )
            mesh = cache[key]
            if mesh is not None:
                stats["meshed_solids"] += 1
                mapper = vtk.vtkPolyDataMapper()
                mapper.SetInputData(mesh)
                actor = vtk.vtkActor()
                actor.SetMapper(mapper)
                ACTOR_SHAPE_NAMES[id(actor)] = shape.GetName()
                ACTOR_NODE_PATHS[id(actor)] = "/".join(path)
                get_inner_radius = getattr(shape, "GetRmin", None)
                ACTOR_INNER_RADII[id(actor)] = (
                    float(get_inner_radius()) if callable(get_inner_radius) else None
                )
                actor.SetUserMatrix(transform)
                color = ROOT.gROOT.GetColor(int(volume.GetLineColor()))
                if color:
                    actor.GetProperty().SetColor(
                        color.GetRed(), color.GetGreen(), color.GetBlue()
                    )

                transparency = volume.GetTransparency()

                if isinstance(transparency, (str, bytes)):
                    transparency = (
                        ord(transparency)
                        if isinstance(transparency, str)
                        else transparency[0]
                    )

                actor.GetProperty().SetOpacity(
                    max(0.0, min(1.0, 1.0 - int(transparency) / 100.0))
                )

                actor.GetProperty().SetRepresentationToSurface()
                if renderer is not None:
                    renderer.AddActor(actor)
                actors.append(actor)
            else:
                stats["failed_solids"] += 1
                skipped.add(shape.GetName())
        for child in children(volume):
            visit(
                child.GetVolume(),
                multiply(vtk, transform, matrix4(vtk, child.GetMatrix())),
                path + (child.GetName(),),
            )

    # Match TGeoNode::Draw(): show selected node in its own coordinate system.
    visit(node.GetVolume(), identity, ())
    missing_nodes = set(include_nodes) - found_nodes
    if missing_nodes:
        missing = ", ".join("/".join(path) for path in sorted(missing_nodes))
        raise ValueError(
            "include_nodes not found below selected geometry node: " + missing
        )
    print("Mesh diagnostics:", dict(stats), file=sys.stderr)
    if skipped:
        print(
            "WARNING: shapes with no renderable polygons:",
            ", ".join(sorted(skipped)),
            file=sys.stderr,
        )
    return actors


def collect_triangles(vtk, actors):
    """Extract transformed world-space triangles from the working VTK meshes."""
    import numpy as np
    from vtk.util.numpy_support import vtk_to_numpy

    batches = []
    all_points = []
    for actor in actors:
        mesh = actor.GetMapper().GetInput()
        if not mesh or mesh.GetNumberOfPolys() == 0:
            continue
        xyz = vtk_to_numpy(mesh.GetPoints().GetData()).astype(np.float64)
        matrix = actor.GetUserMatrix()
        transform = np.array(
            [[matrix.GetElement(i, j) for j in range(4)] for i in range(4)],
            dtype=np.float64,
        )
        xyz = xyz @ transform[:3, :3].T + transform[:3, 3]
        raw = vtk_to_numpy(mesh.GetPolys().GetData())
        # vtkTriangleFilter generates triangles, but accept general polygons too.
        tris = []
        k = 0
        while k < len(raw):
            n = int(raw[k])
            if n < 3 or k + 1 + n > len(raw):
                break
            ids = raw[k + 1 : k + 1 + n]
            for j in range(1, n - 1):
                tris.append((int(ids[0]), int(ids[j]), int(ids[j + 1])))
            k += n + 1
        if not tris:
            continue
        prop = actor.GetProperty()
        color = np.array(prop.GetColor(), dtype=np.float64)
        opacity = float(prop.GetOpacity())
        batches.append((xyz, np.asarray(tris, dtype=np.int64), color, opacity))
        all_points.append(xyz)
    if not batches:
        raise RuntimeError("VTK meshes contained no triangles")
    return batches, np.concatenate(all_points)


def camera_screen_axes(direction, up, expected_axes):
    """Return physical horizontal/vertical axes for an axis-aligned camera.

    Camera signs are retained by cpu_tile through its right/upward vectors.
    Returns None if the view is oblique or does not show the expected plane.
    """
    import numpy as np

    direction = np.asarray(direction, dtype=float)
    up = np.asarray(up, dtype=float)
    if np.linalg.norm(direction) < 1e-12 or np.linalg.norm(up) < 1e-12:
        return None
    forward = -direction / np.linalg.norm(direction)
    if np.linalg.norm(np.cross(forward, up)) < 1e-12:
        return None
    right = np.cross(forward, up)
    right /= np.linalg.norm(right)
    upward = np.cross(right, forward)
    upward /= np.linalg.norm(upward)
    labels = ("X", "Y", "Z")

    def dominant(vector):
        index = int(np.argmax(np.abs(vector)))
        if not np.isclose(abs(vector[index]), 1.0, atol=1e-8):
            return None
        return labels[index]

    axes = (dominant(right), dominant(upward))
    if None in axes or set(axes) != set(expected_axes):
        return None
    return axes


def cpu_tile(
    batches,
    points,
    direction,
    up,
    perspective,
    width,
    height,
    grid=False,
    axis_names=None,
    zoom=1.0,
):
    """Z-buffered flat-shaded CPU rasterizer, with no graphics context."""
    import numpy as np
    from PIL import Image, ImageDraw

    tick_font = load_font(TICK_LABEL_FONT_SIZE)
    axis_font = load_font(AXIS_TITLE_FONT_SIZE)

    def unit(v):
        v = np.asarray(v, dtype=np.float64)
        return v / max(np.linalg.norm(v), 1e-15)

    if not math.isfinite(float(zoom)) or float(zoom) <= 0:
        raise ValueError("Camera zoom must be a finite positive number")
    if np.linalg.norm(direction) < 1e-12:
        raise ValueError("Camera direction cannot be zero")
    forward = -unit(direction)  # camera looks toward the geometry
    if np.linalg.norm(np.cross(forward, up)) < 1e-12:
        raise ValueError("Camera up vector cannot be parallel to direction")
    right = unit(np.cross(forward, up))
    upward = unit(np.cross(right, forward))
    center = 0.5 * (points.min(axis=0) + points.max(axis=0))
    radius = max(float(np.linalg.norm(points - center, axis=1).max()), 1.0)
    distance = 4.5 * radius
    eye = center - forward * distance
    basis = np.stack((right, upward, forward), axis=1)

    def camera_coords(xyz):
        return (xyz - eye) @ basis

    all_cam = camera_coords(points)
    focal = 1.0 / np.tan(np.deg2rad(35.0) / 2.0)

    def projected(cam):
        if perspective:
            z = np.maximum(cam[:, 2], 1e-6)
            return np.column_stack((focal * cam[:, 0] / z, focal * cam[:, 1] / z))
        return cam[:, :2]

    projected_all = projected(all_cam)
    half_width = max(float(np.max(np.abs(projected_all[:, 0]))), 1e-8)
    half_height = max(float(np.max(np.abs(projected_all[:, 1]))), 1e-8)
    # The coordinate frame follows the panel (pad) boundary. All ticks,
    # tick numbers and axis names are placed INSIDE that frame.
    left_margin = 2 if axis_names else 0
    right_margin = 2 if axis_names else 0
    top_margin = 2 if axis_names else 0
    bottom_margin = 2 if axis_names else 0
    plot_left, plot_top = left_margin, top_margin
    plot_right, plot_bottom = width - right_margin, height - bottom_margin
    plot_w, plot_h = plot_right - plot_left, plot_bottom - plot_top
    cx = 0.5 * (plot_left + plot_right)
    cy = 0.5 * (plot_top + plot_bottom)
    # Fit the actual geometry into the available plot region.
    # Leave an internal gutter for tick numbers and axis titles.
    fit_fraction = 0.76 if axis_names else 0.92
    scale = (
        float(zoom)
        * fit_fraction
        * min((plot_w * 0.5) / half_width, (plot_h * 0.5) / half_height)
    )
    zbuffer = np.full((height, width), np.inf, dtype=np.float64)
    pixels = np.full((height, width, 3), 255, dtype=np.uint8)

    # For orthographic projections, horizontal and vertical coordinates are
    # physical ROOT geometry coordinates (cm), not pixel-relative offsets.
    def nice_step(desired):
        exponent = 10.0 ** math.floor(math.log10(max(desired, 1e-12)))
        return (
            min((1.0, 2.0, 5.0, 10.0), key=lambda v: abs(v * exponent - desired))
            * exponent
        )

    if grid and not perspective:
        background = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(background)
        h_axis, v_axis = axis_names
        axis_index = {"X": 0, "Y": 1, "Z": 2}
        # Camera right/up match the requested axes for all three views.
        h_sign = float(right[axis_index[h_axis]])
        v_sign = float(upward[axis_index[v_axis]])
        h_center = float(center[axis_index[h_axis]])
        v_center = float(center[axis_index[v_axis]])
        h_min = h_center + (plot_left - cx) / (scale * h_sign)
        h_max = h_center + (plot_right - cx) / (scale * h_sign)
        v_top = v_center + (cy - plot_top) / (scale * v_sign)
        v_bottom = v_center + (cy - plot_bottom) / (scale * v_sign)
        step = nice_step(85.0 / scale)

        def ticks(a, b):
            low, high = sorted((a, b))
            start = math.ceil((low - 1e-9 * step) / step)
            stop = math.floor((high + 1e-9 * step) / step)
            return [k * step for k in range(start, stop + 1)]

        for value in ticks(h_min, h_max):
            px = cx + (value - h_center) * h_sign * scale
            color = (184, 194, 206) if abs(value) < step * 1e-8 else (230, 234, 239)
            draw.line(
                (round(px), plot_top, round(px), plot_bottom), fill=color, width=1
            )
        for value in ticks(v_top, v_bottom):
            py = cy - (value - v_center) * v_sign * scale
            color = (184, 194, 206) if abs(value) < step * 1e-8 else (230, 234, 239)
            draw.line(
                (plot_left, round(py), plot_right, round(py)), fill=color, width=1
            )
        pixels = np.asarray(background, dtype=np.uint8).copy()
    light = unit((0.35, -0.45, 0.82))

    # Rasterize opaque surfaces first. Transparent surfaces are approximated
    # by alpha blending when they pass the opaque depth test.
    surfaces = sorted(batches, key=lambda b: b[3] < 0.999)
    triangle_count = 0
    for xyz, triangles, color, opacity in surfaces:
        cam = camera_coords(xyz)
        xy = projected(cam)
        xy[:, 0] = cx + xy[:, 0] * scale
        xy[:, 1] = cy - xy[:, 1] * scale
        for ids in triangles:
            p = xy[ids]
            z = cam[ids, 2]
            if np.any(z <= 1e-5):
                continue
            minx = max(0, int(np.floor(p[:, 0].min())))
            maxx = min(width - 1, int(np.ceil(p[:, 0].max())))
            miny = max(0, int(np.floor(p[:, 1].min())))
            maxy = min(height - 1, int(np.ceil(p[:, 1].max())))
            if maxx < minx or maxy < miny:
                continue
            x0, y0 = p[0]
            x1, y1 = p[1]
            x2, y2 = p[2]
            det = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
            if abs(det) < 1e-10:
                continue
            yy, xx = np.mgrid[miny : maxy + 1, minx : maxx + 1]
            xx = xx + 0.5
            yy = yy + 0.5
            w0 = ((y1 - y2) * (xx - x2) + (x2 - x1) * (yy - y2)) / det
            w1 = ((y2 - y0) * (xx - x2) + (x0 - x2) * (yy - y2)) / det
            w2 = 1.0 - w0 - w1
            inside = (w0 >= -1e-8) & (w1 >= -1e-8) & (w2 >= -1e-8)
            if not inside.any():
                continue
            if perspective:
                invz = w0 / z[0] + w1 / z[1] + w2 / z[2]
                depth = 1.0 / np.maximum(invz, 1e-12)
            else:
                depth = w0 * z[0] + w1 * z[1] + w2 * z[2]
            old = zbuffer[miny : maxy + 1, minx : maxx + 1]
            mask = inside & (depth < old)
            if not mask.any():
                continue
            normal = np.cross(xyz[ids[1]] - xyz[ids[0]], xyz[ids[2]] - xyz[ids[0]])
            normal = unit(normal)
            # Two-sided shading tolerates inconsistent ROOT polygon winding.
            brightness = 0.30 + 0.70 * abs(float(np.dot(normal, light)))
            rgb = np.clip(255 * color * brightness, 0, 255)
            patch = pixels[miny : maxy + 1, minx : maxx + 1]
            if opacity >= 0.999:
                patch[mask] = rgb.astype(np.uint8)
                old[mask] = depth[mask]
            else:
                patch[mask] = np.clip(
                    opacity * rgb + (1.0 - opacity) * patch[mask], 0, 255
                ).astype(np.uint8)
            triangle_count += 1
    tile = Image.fromarray(pixels, "RGB")
    if axis_names:
        draw = ImageDraw.Draw(tile)
        ink = (48, 57, 70)
        draw.rectangle(
            (plot_left, plot_top, plot_right, plot_bottom), outline=ink, width=1
        )

        def tick_label(value):
            if abs(value) < step * 1e-8:
                return "0"
            return "%.8g" % value

        # Tick marks and numeric labels point inward from the bottom and
        # left edges. The frame coincides with the pad boundary.
        tick_length = 7
        for value in ticks(h_min, h_max):
            px = cx + (value - h_center) * h_sign * scale
            px = round(px)
            draw.line(
                (px, plot_bottom, px, plot_bottom - tick_length), fill=ink, width=1
            )
            label = tick_label(value)
            bbox = draw.textbbox((0, 0), label, font=tick_font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            if plot_left + tw / 2 + 3 <= px <= plot_right - tw / 2 - 3:
                draw.text(
                    (round(px - tw / 2), plot_bottom - tick_length - th - 6),
                    label,
                    fill=ink,
                    font=tick_font,
                )
        for value in ticks(v_top, v_bottom):
            py = cy - (value - v_center) * v_sign * scale
            py = round(py)
            draw.line((plot_left, py, plot_left + tick_length, py), fill=ink, width=1)
            label = tick_label(value)
            bbox = draw.textbbox((0, 0), label, font=tick_font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            if plot_top + th / 2 + 3 <= py <= plot_bottom - th / 2 - 3:
                draw.text(
                    (plot_left + tick_length + 5, round(py - th / 2)),
                    label,
                    fill=ink,
                    font=tick_font,
                )
        # Axis names also sit within the frame, clear of the tick labels.
        h_title = axis_names[0] + " (cm)"
        v_title = axis_names[1] + " (cm)"
        hb = draw.textbbox((0, 0), h_title, font=axis_font)
        draw.text(
            (plot_right - (hb[2] - hb[0]) - 12, plot_bottom - 15),
            h_title,
            fill=ink,
            font=axis_font,
        )
        draw.text((plot_left + 12, plot_top + 25), v_title, fill=ink, font=axis_font)
    projection = {
        "center": center,
        "right": right,
        "upward": upward,
        "cx": cx,
        "cy": cy,
        "scale": scale,
        "axis_names": axis_names,
    }
    return tile, triangle_count, projection


def format_dimension_label(definition, value, axis):
    """Format a dimension label, using its configured name by default."""
    template = definition.get("label", "{name} = {value:.2f} cm")
    return template.format(name=definition.get("name", axis), value=value, axis=axis)


def _dimension_reference(spec, solids, indices):
    """Resolve a configured point from placed-solid metadata and mesh vertices."""
    import numpy as np

    if not solids:
        raise ValueError("no placed solid with shape %r" % spec["shape"])
    instance = spec.get("instance", "all")
    if instance == "all":
        selected = solids
    elif instance == "closest_to_center":
        center_axis = spec.get("center_axis")
        if center_axis is not None:
            center_axis = str(center_axis).upper()
            if center_axis not in indices:
                raise ValueError("center_axis must be X, Y or Z")

        def center_distance(solid):
            vertices = solid["vertices"]
            middle = 0.5 * (vertices.min(axis=0) + vertices.max(axis=0))
            if center_axis is not None:
                return abs(float(middle[indices[center_axis]]))
            return float(np.linalg.norm(middle))

        selected = [min(solids, key=center_distance)]
    elif instance in ("leftmost", "rightmost", "bottommost", "topmost"):
        coord = 0 if instance in ("leftmost", "rightmost") else 1
        key = lambda solid: (
            0.5
            * (solid["vertices"][:, coord].min() + solid["vertices"][:, coord].max())
        )
        selected = [
            (min if instance in ("leftmost", "bottommost") else max)(solids, key=key)
        ]
    else:
        raise ValueError("unsupported instance selector %r" % instance)

    point_mode = spec.get("point", "center")
    if point_mode == "inner_radius":
        if len(selected) != 1:
            raise ValueError(
                "inner_radius requires an instance selecting one placed solid"
            )
        solid = selected[0]
        radius = solid.get("inner_radius")
        if radius is None:
            raise ValueError("shape %r has no inner radius" % spec["shape"])
        radial_axis = str(spec.get("radial_axis", "X")).upper()
        if radial_axis not in ("X", "Y"):
            raise ValueError("radial_axis must be X or Y for a tube")
        return (
            solid["translation"] + solid["rotation"][:, indices[radial_axis]] * radius
        )

    vertices = np.concatenate([solid["vertices"] for solid in selected])
    low, high = vertices.min(axis=0), vertices.max(axis=0)
    result = (low + high) / 2.0
    if point_mode != "center":
        mode, _, axis = point_mode.partition("_")
        if mode not in ("min", "max") or axis.upper() not in indices:
            raise ValueError("unsupported reference point %r" % point_mode)
        result[indices[axis.upper()]] = (low if mode == "min" else high)[
            indices[axis.upper()]
        ]
    return result


def _dimension_node_matches(actor_path, selected_path):
    """Match a relative node path and all solids below that node."""
    if isinstance(selected_path, str):
        selected_path = tuple(part for part in selected_path.split("/") if part)
    else:
        selected_path = tuple(selected_path)
    actor_path = tuple(part for part in actor_path.split("/") if part)
    return bool(selected_path) and actor_path[: len(selected_path)] == selected_path


def draw_dimension_overlays(tile, pad_key, projection, actors):
    """Render configured dimensions with common arrow, witness-line and label styling.

    Reference coordinates are computed from transformed TGeo shape vertices in cm.
    This is the only routine responsible for dimension overlay rendering.
    """
    import numpy as np
    from PIL import ImageDraw
    from vtk.util.numpy_support import vtk_to_numpy

    definitions = DIMENSIONS.get(pad_key, ())
    if not definitions:
        return

    # Actual horizontal and vertical physical axes, derived from the camera.
    camera_axes = projection.get("axis_names")
    if camera_axes is None:
        return
    indices = {"X": 0, "Y": 1, "Z": 2}
    center = np.asarray(projection["center"], dtype=float)
    right = np.asarray(projection["right"], dtype=float)
    upward = np.asarray(projection["upward"], dtype=float)
    cx, cy, scale = (projection[k] for k in ("cx", "cy", "scale"))

    # Each actor represents one placed solid, even when its TGeoShape is shared.
    placements = {}
    for actor in actors:
        name = ACTOR_SHAPE_NAMES.get(id(actor))
        if not name:
            continue
        mesh = actor.GetMapper().GetInput()
        if not mesh or not mesh.GetPoints():
            continue
        xyz = vtk_to_numpy(mesh.GetPoints().GetData()).astype(np.float64)
        m = actor.GetUserMatrix()
        rotation = np.array(
            [[m.GetElement(i, j) for j in range(3)] for i in range(3)], dtype=float
        )
        translation = np.array([m.GetElement(i, 3) for i in range(3)])
        placements.setdefault(name, []).append(
            {
                "vertices": xyz @ rotation.T + translation,
                "rotation": rotation,
                "translation": translation,
                "inner_radius": ACTOR_INNER_RADII.get(id(actor)),
                "node_path": ACTOR_NODE_PATHS.get(id(actor), ""),
            }
        )

    def reference(spec):
        solids = placements.get(spec["shape"], [])
        if "node" in spec:
            solids = [
                solid
                for solid in solids
                if _dimension_node_matches(solid["node_path"], spec["node"])
            ]
        return _dimension_reference(spec, solids, indices)

    def pixel(point):
        delta = point - center
        return np.array(
            [cx + np.dot(delta, right) * scale, cy - np.dot(delta, upward) * scale],
            dtype=float,
        )

    draw = ImageDraw.Draw(tile)
    font = load_font(DIMENSION_FONT_SIZE)
    ink = DIMENSION_COLOR

    def dotted(start, end):
        start, end = np.asarray(start, dtype=float), np.asarray(end, dtype=float)
        delta = end - start
        length = float(np.linalg.norm(delta))
        if length < 1e-8:
            return
        unit = delta / length
        dash, gap = DIMENSION_EXTENSION_DASH_PX
        position = 0.0
        while position < length:
            stop = min(length, position + max(1, dash))
            p, q = start + position * unit, start + stop * unit
            draw.line((tuple(p), tuple(q)), fill=ink, width=DIMENSION_EXTENSION_WIDTH)
            position += max(1, dash + gap)

    for definition in definitions:
        try:
            radial = any(
                endpoint.get("point") == "inner_radius"
                for endpoint in (definition["from"], definition["to"])
            )
            axis = str(definition["axis"]).upper()
            if radial:
                if axis not in ("R", "X", "Y", "Z"):
                    raise ValueError("radial dimension axis must be R, X, Y or Z")
            elif axis not in camera_axes:
                raise ValueError("%s is not an axis in the %s pad" % (axis, pad_key))
            side = definition.get(
                "side", "right" if axis == camera_axes[1] else "bottom"
            )
            if not radial and axis == camera_axes[0] and side not in ("top", "bottom"):
                raise ValueError("horizontal dimension needs top/bottom side")
            if not radial and axis == camera_axes[1] and side not in ("left", "right"):
                raise ValueError("vertical dimension needs left/right side")
            p1, p2 = reference(definition["from"]), reference(definition["to"])
            value = (
                float(np.linalg.norm(p2 - p1))
                if radial
                else abs(float(p2[indices[axis]] - p1[indices[axis]]))
            )
            a, b = pixel(p1), pixel(p2)
            offset = float(definition.get("offset_px", DIMENSION_OFFSET_PX))
            anchor = 0.0
            if radial:
                start, end = a, b
            elif axis == camera_axes[0]:
                # Horizontal measurement; vertical dotted witness lines.
                anchor = (
                    max(a[1], b[1]) + offset
                    if side == "bottom"
                    else min(a[1], b[1]) - offset
                )
                anchor = max(22.0, min(tile.height - 22.0, anchor))
                start, end = np.array([a[0], anchor]), np.array([b[0], anchor])
                overhang = DIMENSION_EXTENSION_OVERHANG_PX * (
                    1 if side == "bottom" else -1
                )
                dotted(a, (a[0], anchor + overhang))
                dotted(b, (b[0], anchor + overhang))
            else:
                # Vertical measurement; horizontal dotted witness lines.
                anchor = (
                    max(a[0], b[0]) + offset
                    if side == "right"
                    else min(a[0], b[0]) - offset
                )
                anchor = max(22.0, min(tile.width - 22.0, anchor))
                start, end = np.array([anchor, a[1]]), np.array([anchor, b[1]])
                overhang = DIMENSION_EXTENSION_OVERHANG_PX * (
                    1 if side == "right" else -1
                )
                dotted(a, (anchor + overhang, a[1]))
                dotted(b, (anchor + overhang, b[1]))

            draw.line((tuple(start), tuple(end)), fill=ink, width=DIMENSION_LINE_WIDTH)
            vec = end - start
            length = float(np.linalg.norm(vec))
            if length < 1e-8:
                raise ValueError("dimension reference points coincide on screen")
            direction = vec / length
            perp = np.array([-direction[1], direction[0]])
            for tip, inward in ((start, direction), (end, -direction)):
                back = tip + inward * min(DIMENSION_ARROW_LENGTH_PX, length / 3)
                half = DIMENSION_ARROW_HALF_WIDTH_PX
                draw.polygon(
                    [tuple(tip), tuple(back + perp * half), tuple(back - perp * half)],
                    fill=ink,
                )

            label = format_dimension_label(definition, value, axis)
            bbox = draw.textbbox((0, 0), label, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            midpoint = (start + end) * 0.5
            if radial:
                normal = np.array([-direction[1], direction[0]])
                label_center = midpoint - normal * (th / 2 + 8)
                lx, ly = label_center[0] - tw / 2, label_center[1] - th / 2
            elif axis == camera_axes[0]:
                lx, ly = midpoint[0] - tw / 2, anchor - th - 12
            else:
                lx, ly = anchor - tw - 12, midpoint[1] - th / 2
            lx = max(5, min(tile.width - tw - 5, lx))
            ly = max(5, min(tile.height - th - 5, ly))
            draw.rectangle((lx - 3, ly - 3, lx + tw + 3, ly + th + 3), fill="white")
            draw.text((lx, ly), label, fill=ink, font=font)
            print(
                "%s: %s = %.4f cm" % (pad_key, definition.get("name", axis), value),
                file=sys.stderr,
            )
        except (ValueError, KeyError) as exc:
            print(
                "WARNING: %s dimension %r skipped: %s"
                % (pad_key, definition.get("name", "?"), exc),
                file=sys.stderr,
            )


def render_four(vtk, actors, filename, width=1600, height=1200):
    from PIL import Image, ImageDraw

    batches, points = collect_triangles(vtk, actors)
    pad_title_font = load_font(PAD_TITLE_FONT_SIZE)
    # Three equal-height pads on the left; XOY fills the right column.
    if not 0.0 < LEFT_COLUMN_FRACTION < 1.0:
        raise ValueError("LEFT_COLUMN_FRACTION must be between 0 and 1")
    left_width = round(width * LEFT_COLUMN_FRACTION)
    right_width = width - left_width
    row_edges = [0, height // 3, (2 * height) // 3, height]
    panels = [
        (
            "Perspective",
            "Perspective",
            None,
            (0, row_edges[0], left_width, row_edges[1] - row_edges[0]),
        ),
        (
            "Orthographic ZOY",
            "ZOY",
            ("Y", "Z"),
            (0, row_edges[1], left_width, row_edges[2] - row_edges[1]),
        ),
        (
            "Orthographic ZOX",
            "ZOX",
            ("X", "Z"),
            (0, row_edges[2], left_width, row_edges[3] - row_edges[2]),
        ),
        ("Orthographic XOY", "XOY", ("X", "Y"), (left_width, 0, right_width, height)),
    ]
    result = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(result)
    for title, key, axes, (x, y, w, h) in panels:
        camera = CAMERA_VIEWS[key]
        perspective = bool(camera["perspective"])
        # Derive physical horizontal/vertical axes from the current camera,
        # rather than assuming the original orientation of each pad.
        axis_names = None
        if axes is not None and not perspective:
            axis_names = camera_screen_axes(camera["direction"], camera["up"], axes)
            if axis_names is None:
                print(
                    "NOTE: %s has an oblique camera; calibrated frame and dimensions hidden."
                    % key,
                    file=sys.stderr,
                )
        tile, count, projection = cpu_tile(
            batches,
            points,
            camera["direction"],
            camera["up"],
            perspective=perspective,
            width=w,
            height=h,
            grid=axis_names is not None,
            axis_names=axis_names,
            zoom=camera["zoom"],
        )
        if axis_names is not None:
            draw_dimension_overlays(tile, key, projection, actors)
        ImageDraw.Draw(tile).text(
            (14, 14), title, fill=(30, 38, 49), font=pad_title_font
        )
        result.paste(tile, (x, y))
        print(
            "Rendered %s: %d visible triangle passes" % (title, count), file=sys.stderr
        )
    # Subtle panel separators.
    draw.line((left_width, 0, left_width, height), fill=(185, 190, 197), width=2)
    for boundary in row_edges[1:-1]:
        draw.line((0, boundary, left_width, boundary), fill=(185, 190, 197), width=2)
    result.save(filename, dpi=(OUTPUT_DPI, OUTPUT_DPI))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("geometry_file", nargs="?", default=DEFAULT_GEOMETRY)
    p.add_argument("output_file", nargs="?", default=DEFAULT_OUTPUT)
    args = p.parse_args()
    if os.path.abspath(args.geometry_file) == os.path.abspath(args.output_file):
        p.error("Input and output paths must differ")
    import ROOT

    ROOT.gROOT.SetBatch(True)
    import vtk

    install_root_buffer_bridge(ROOT)
    f, geometry = open_geometry(ROOT, args.geometry_file)
    support = find_support(geometry.GetTopNode())
    if support is None:
        raise RuntimeError("Support node not found: " + "/".join(PATH))
    actors = build_actors(ROOT, vtk, support, None)
    if not actors:
        raise RuntimeError(
            "No renderable solid surfaces found; inspect Mesh diagnostics above. "
            "Inspect the failed-shape warnings for missing buffers or unsupported shapes."
        )
    png = (
        args.output_file[:-5] + ".png"
        if args.output_file.endswith(".root")
        else args.output_file + ".png"
    )
    render_four(vtk, actors, png)
    # Save a self-contained ROOT canvas with the resulting raster image.
    image = ROOT.TImage.Open(png)
    if not image:
        raise RuntimeError("Could not read generated PNG for ROOT output")
    canvas = ROOT.TCanvas("sts_capture", "STS carbon-fibre support", 1600, 1200)
    image.Draw()
    canvas.Modified()
    canvas.Update()
    out = ROOT.TFile.Open(args.output_file, "RECREATE")
    if not out or out.IsZombie():
        raise RuntimeError("Cannot create output ROOT file")
    canvas.Write("sts_capture")
    ROOT.TNamed("geometry_file", args.geometry_file).Write()
    ROOT.TNamed("geometry_node", "/".join(PATH)).Write()
    out.Close()
    print("Wrote", png, "and", args.output_file)
    f.Close()


if __name__ == "__main__":
    import traceback

    try:
        raise SystemExit(main())
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
