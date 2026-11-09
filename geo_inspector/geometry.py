"""Lazy PyROOT helpers for opening and navigating TGeo geometry files."""


def children(volume):
    nodes = volume.GetNodes()
    if nodes:
        for index in range(nodes.GetEntriesFast()):
            node = nodes.At(index)
            if node:
                yield node


def open_geometry(filename, root=None):
    """Open a ROOT file and return ``(file_handle, TGeoManager)``.

    PyROOT is imported only when this function is called. The returned file
    handle must remain open while geometry objects are being used.
    """
    if root is None:
        import ROOT as root
    file_handle = root.TFile.Open(str(filename), "READ")
    if not file_handle or file_handle.IsZombie():
        raise RuntimeError("Cannot open ROOT file: %s" % filename)
    keys = list(file_handle.GetListOfKeys())
    for key in keys:
        cls = root.TClass.GetClass(key.GetClassName())
        if cls and cls.InheritsFrom(root.TGeoManager.Class()):
            geometry = key.ReadObj()
            root.gGeoManager = geometry
            return file_handle, geometry
    geometry = root.TGeoManager("geo_inspector_geometry", "Imported geometry")
    for key in keys:
        cls = root.TClass.GetClass(key.GetClassName())
        if cls and cls.InheritsFrom(root.TGeoVolume.Class()):
            volume = key.ReadObj()
            visited = set()

            def register(current):
                address = root.addressof(current)
                if address in visited:
                    return
                visited.add(address)
                geometry.AddVolume(current)
                for child in children(current):
                    register(child.GetVolume())

            register(volume)
            geometry.SetTopVolume(volume)
            geometry.CloseGeometry()
            root.gGeoManager = geometry
            return file_handle, geometry
    file_handle.Close()
    raise RuntimeError("No TGeoManager or TGeoVolume found in %s" % filename)


def find_node(top_node, path):
    """Find a node by a sequence of node names, optionally including root."""
    names = tuple(path.split("/")) if isinstance(path, str) else tuple(path)
    names = tuple(name for name in names if name)
    if not names:
        return top_node
    offset = 1 if names[0] == top_node.GetName() else 0
    if offset:
        names = names[1:]
    current = top_node
    for name in names:
        current = next(
            (node for node in children(current.GetVolume()) if node.GetName() == name),
            None,
        )
        if current is None:
            return None
    return current


def list_nodes(top_node):
    """Yield ``(absolute node path, node)`` pairs depth-first."""

    def visit(node, parent):
        path = parent + (node.GetName(),)
        yield "/" + "/".join(path), node
        for child in children(node.GetVolume()):
            yield from visit(child, path)

    yield from visit(top_node, ())
