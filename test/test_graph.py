import pytest

from gitfourchette.graph import Graph, Frame
from .test_graphsplicing import parseAncestryOneLiner


def findSolvedArc(frame, openedBy, closedBy):
    for a in frame.solvedArcs:
        if not a:
            continue
        if a.openedBy == openedBy and a.closedBy == closedBy:
            return a
    assert False, f"did not find solved arc {openedBy} -> {closedBy} in frame {frame.row}"


def findOpenArc(frame, openedBy, closedBy):
    for a in frame.openArcs:
        if not a:
            continue
        if a.openedBy == openedBy and a.closedBy == closedBy:
            return a
    assert False, f"did not find open arc {openedBy} -> {closedBy} in frame {frame.row}"


def checkFrame(pb, row, commit, solved="", open=""):
    pb.advanceToNextRow()
    frame = pb.copyCleanFrame()

    assert frame.row == row
    assert frame.commit == commit

    numSolved = 0
    numOpen = 0
    if solved:
        for sa in solved.split(","):
            numSolved += 1
            findSolvedArc(frame, *sa.split("-"))
    if open:
        for oa in open.split(","):
            numOpen += 1
            findOpenArc(frame, *oa.split("-"))

    assert numSolved == sum(1 for sa in frame.solvedArcs if sa is not None), "there are more solved arcs to test"
    assert numOpen == sum(1 for oa in frame.openArcs if oa is not None), "there are more open arcs to test"

    return frame


def getNextFrame(pb):
    pb.advanceToNextRow()
    return pb.copyCleanFrame()


def testGraph1():
    """

    a1
     |
    a2
     |
     |  b1
     |   |
     |  b2
     |   |
    a3__/
     |
    a4

    """
    sequence, parentMap, heads = parseAncestryOneLiner("a1,a2 a2,a3 b1,b2 b2,a3 a3,a4 a4")

    g = Graph()
    g.generateFullSequence(sequence, parentMap)
    print("\n" + g.textDiagram())
    pb = g.startPlayback(0)

    checkFrame(pb, 0, "a1", open="a1-a2")
    checkFrame(pb, 1, "a2", solved="a1-a2", open="a2-a3")
    checkFrame(pb, 2, "b1", open="a2-a3,b1-b2")
    checkFrame(pb, 3, "b2", solved="b1-b2", open="b2-a3,a2-a3")
    checkFrame(pb, 4, "a3", solved="b2-a3,a2-a3", open="a3-a4")
    checkFrame(pb, 5, "a4", solved="a3-a4")


def testGapBetweenBranches():
    """

    a1
     |
     |  b1
     |   |
     |   |  c1
     |   |   |
    a2__/    |
     |       |
     |      c2
     |       |
     f______/

    """

    sequence, parentMap, heads = parseAncestryOneLiner("a1,a2 b1,a2 c1,c2 a2,f c2,f f")

    g = Graph()
    g.generateFullSequence(sequence, parentMap)
    print("\n" + g.textDiagram())
    pb = g.startPlayback(0)

    checkFrame(pb, 0, "a1", open="a1-a2")
    checkFrame(pb, 1, "b1", open="a1-a2,b1-a2")
    checkFrame(pb, 2, "c1", open="a1-a2,b1-a2,c1-c2")
    checkFrame(pb, 3, "a2", solved="a1-a2,b1-a2", open="c1-c2,a2-f")
    frameC2 = checkFrame(pb, 4, "c2", solved="c1-c2", open="a2-f,c2-f")
    checkFrame(pb, 5, "f", solved="a2-f,c2-f")

    laneRemap, numFlattenedLanes = frameC2.flattenLanes([])
    assert laneRemap[0] == (0, 0)
    assert laneRemap[2] == (1, 1)


def testNewBranchInGap():
    """
    Flattening OFF:         Flattening ON:

    a1                      a1
     |                       |
     |  b1                   |  b1
     |   |                   |   |
     |   |  c1               |   |  c1
     |   |   |               |   |   |
    a2__/    |              a2__/    |
     |       |               |       |
     |      c2               |      c2
     |       |               |     /
     |  d1   |               |    /   d1
     |   |   |               |    |    |
    a3   |   |              a3    |    |
     |   |   |               |    |    |
     f__/___/                f___/____/

    """

    sequence, parentMap, heads = parseAncestryOneLiner("a1,a2 b1,a2 c1,c2 a2,a3 c2,f d1,f a3,f f")

    g = Graph()
    g.generateFullSequence(sequence, parentMap)
    print("\n" + g.textDiagram())
    pb = g.startPlayback(0)

    frameA1 = checkFrame(pb, 0, "a1", open="a1-a2")
    frameB1 = checkFrame(pb, 1, "b1", open="a1-a2,b1-a2")
    frameC1 = checkFrame(pb, 2, "c1", open="a1-a2,b1-a2,c1-c2")
    frameA2 = checkFrame(pb, 3, "a2", solved="a1-a2,b1-a2", open="c1-c2,a2-a3")
    frameC2 = checkFrame(pb, 4, "c2", solved="c1-c2", open="a2-a3,c2-f")
    frameD1 = checkFrame(pb, 5, "d1", open="a2-a3,c2-f,d1-f")
    frameA3 = checkFrame(pb, 6, "a3", solved="a2-a3", open="a3-f,c2-f,d1-f")
    frameF = checkFrame(pb, 7, "f", solved="a3-f,c2-f,d1-f")

    laneRemap, numFlattenedLanes = frameA2.flattenLanes([])
    print("Frame A2:", laneRemap)
    assert laneRemap[0] == (0, 0)  # A1-A2 in column 0
    assert laneRemap[1] == (1, -1)  # B1 comes from above in column 1, frees up column 1 as it merges into A2
    assert laneRemap[2] == (2, 1)  # C1 comes from above in column 2, and gets remapped to column 1 below

    laneRemap, numFlattenedLanes = frameC2.flattenLanes([])
    print("Frame C2:", laneRemap)
    assert laneRemap[0] == (0, 0)  # A2-A3 in column 0
    assert laneRemap[2] == (1, 1)  # C2 is in lane 2, but it can use the gap in column 1 left by vacant lane 1

    laneRemap, numFlattenedLanes = frameD1.flattenLanes([])
    print("Frame D1:", laneRemap)
    assert laneRemap[0] == (0, 0)
    assert laneRemap[2] == (1, 1)  # c1 still
    assert laneRemap[1] == (-1, 2)  # tip
