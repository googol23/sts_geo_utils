"""Navigation works on TGeo-like objects without importing ROOT."""

from geo_inspector import children, find_node, list_nodes


class Nodes:
    def __init__(self, nodes):
        self.nodes = nodes

    def GetEntriesFast(self):
        return len(self.nodes)

    def At(self, index):
        return self.nodes[index]


class Node:
    def __init__(self, name, *nodes):
        self.name, self.nodes = name, nodes

    def GetName(self):
        return self.name

    def GetVolume(self):
        return self

    def GetNodes(self):
        return Nodes(self.nodes)


def test_navigation_without_root():
    sensor = Node("Sensor01_1")
    ladder = Node("Ladder_1", sensor)
    top = Node("TOP_1", ladder, Node("Other_1"))
    assert list(children(top)) == [ladder, top.nodes[1]]
    assert find_node(top, "/TOP_1/Ladder_1/Sensor01_1") is sensor
    assert find_node(top, "Ladder_1/Sensor01_1") is sensor
    assert find_node(top, "/") is top
    assert find_node(top, "missing") is None
    paths = [path for path, _ in list_nodes(top)]
    assert paths == [
        "/TOP_1",
        "/TOP_1/Ladder_1",
        "/TOP_1/Ladder_1/Sensor01_1",
        "/TOP_1/Other_1",
    ]
