from gitfourchette import colors
from gitfourchette import log
from gitfourchette import settings
from gitfourchette.graph import Frame, Graph
from gitfourchette.qt import *
from gitfourchette.repostate import RepoState, UC_FAKEID
from itertools import zip_longest
from pygit2 import Commit, Oid


LANE_WIDTH = 10
LANE_THICKNESS = 2
DOT_RADIUS = 3
UC_COLOR = colors.gray
UC_STIPPLE = 12
ABRIDGMENT_THRESHOLD = 50


def getColor(laneID):
    return colors.rainbowBright[laneID % len(colors.rainbowBright)]


def flattenLanes(frame: Frame, hiddenCommits: set[Oid]) -> tuple[list[tuple[int, int]], int]:
    """
    Compute columns (horizontal positions) for each lane above and below this row.
    """

    if settings.prefs.graph_flattenLanes:
        laneRemap, flatTotal = frame.flattenLanes(hiddenCommits)
    else:
        # Straightforward lane positions (lane column == lane ID)
        laneRemap = []
        for i, (cl, ol) in enumerate(zip_longest(frame.solvedArcs, frame.openArcs)):
            laneRemap.append( (i, i) )
        flatTotal = len(laneRemap)

    return laneRemap, flatTotal


def getCommitBulletColumn(
        commitLane: int,
        flatTotal: int,
        lanePositionsAB: list[tuple[int, int]]
) -> tuple[int, int]:
    # Find out at which position to draw the commit's bullet point.
    myLanePosition = -1

    if commitLane < len(lanePositionsAB):
        posA, posB = lanePositionsAB[commitLane]

        # First, attempt to put bullet point in parent lane's position (below).
        if myLanePosition < 0:
            myLanePosition = posB

        # If that didn't work (commit has no parents), put bullet point in child lane's position (above).
        if myLanePosition < 0:
            myLanePosition = posA

    # If that still didn't work, we have a lone commit without parents or children; just toss the bullet to the right.
    if myLanePosition < 0:
        flatTotal += 1
        myLanePosition = flatTotal
        #assert myLanePosition == commitLane, "expecting GraphGenerator to put lone commits on the rightmost column"

    return myLanePosition, flatTotal


def paintGraphFrame(
        state: RepoState,
        oid: Oid,
        painter: QPainter,
        rect: QRect,
        outlineColor: QColor
):
    if not state.graph:
        return

    try:
        # Get this commit's sequential index in the graph
        myRow = state.graph.getCommitRow(oid)
    except KeyError:
        log.warning("graphpaint", "skipping unregistered commit:", oid)
        return
    except IndexError:
        log.warning("graphpaint", "skipping commit that is probably not registered yet:", oid)
        return

    painter.save()
    painter.setRenderHints(QPainter.RenderHint.Antialiasing, True)

    # Ensure all coordinates below are integers so our straight lines don't look blurry
    x = int(rect.left() + LANE_WIDTH // 2)
    top = int(rect.y())
    bottom = int(rect.y() + rect.height())  # Don't use rect.bottom(), which for historical reasons doesn't return what we want (see Qt docs)
    middle = (top + bottom) // 2

    # Get graph frame for this row
    frame = state.graph.getFrame(myRow)
    assert frame.commit == oid
    assert frame.row == myRow

    # Get the commit's lane ID
    commitLane = frame.getHomeLaneForCommit()

    # Flatten the lanes so there are no horizontal gaps in-between the lanes (optional).
    # laneColumnsAB is a table of lanes to columns (horizontal positions).
    laneColumnsAB, numFlattenedColumns = flattenLanes(frame, state.hiddenCommits)#laneContinuity)

    # Get column (horizontal position) of commit bullet point.
    myColumn, numFlattenedColumns = getCommitBulletColumn(commitLane, numFlattenedColumns, laneColumnsAB)

    rect.setRight(x + numFlattenedColumns * LANE_WIDTH)
    mx = x + myColumn * LANE_WIDTH  # the screen X of this commit's bullet point

    # draw bullet point _outline_ for this commit, beneath everything else
    painter.setPen(QPen(outlineColor, 2, Qt.PenStyle.SolidLine))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(QPoint(mx, middle), DOT_RADIUS, DOT_RADIUS)

    path = QPainterPath()

    def submitPath(path: QPainterPath, column, stipple=False, dashOffset = 0):
        if path.isEmpty():
            return
        # white outline
        painter.setPen(QPen(outlineColor, LANE_THICKNESS + 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap, Qt.PenJoinStyle.BevelJoin))
        painter.drawPath(path)
        # actual color
        color = UC_COLOR if stipple else getColor(column)
        pen = QPen(color, LANE_THICKNESS, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap, Qt.PenJoinStyle.BevelJoin)
        if stipple:
            interval = rect.height()/(UC_STIPPLE*LANE_THICKNESS)
            pen.setDashPattern([interval, interval])
            pen.setDashOffset(dashOffset * 0.5 * rect.height()/(LANE_THICKNESS))
        painter.setPen(pen)
        painter.drawPath(path)
        # clear path for next iteration
        path.clear()

    arcsPassingByCommit = [arc for arc in frame.getArcsPassingByCommit() if not arc.connectsHiddenCommit(state.hiddenCommits)]
    arcsOpenedByCommit = [arc for arc in frame.getArcsOpenedByCommit() if not arc.connectsHiddenCommit(state.hiddenCommits)]
    arcsClosedByCommit = [arc for arc in frame.getArcsClosedByCommit() if not arc.connectsHiddenCommit(state.hiddenCommits)]

    # draw arcs PASSING BY commit
    for arc in arcsPassingByCommit:
        columnA, columnB = laneColumnsAB[arc.lane]  # column above, column below
        ax = x + columnA * LANE_WIDTH
        bx = x + columnB * LANE_WIDTH
        path.moveTo(ax, top)
        path.cubicTo(ax, middle, bx, middle, bx, bottom)
        submitPath(path, arc.lane, arc.openedBy == UC_FAKEID)

    # draw arcs CLOSED BY commit (from above)
    for arc in reversed(arcsClosedByCommit):
        columnA, _ = laneColumnsAB[arc.lane]  # column above, column below
        ax = x + columnA * LANE_WIDTH
        # Path from above does elbow shape to merge into commit bullet point
        path.moveTo(ax, top)
        path.quadTo(ax, middle, mx, middle)
        submitPath(path, arc.lane, arc.openedBy == UC_FAKEID)

    # draw arcs OPENED BY commit (downwards)
    for arc in reversed(arcsOpenedByCommit):
        _, columnB = laneColumnsAB[arc.lane]  # column above, column below
        bx = x + columnB * LANE_WIDTH
        # Path forks downward from commit bullet point
        path.moveTo(mx, middle)
        path.quadTo(bx, middle, bx, bottom)
        submitPath(path, arc.lane, arc.openedBy == UC_FAKEID, dashOffset=1)

    # draw arc junctions
    for arc in arcsPassingByCommit:
        for j in arc.junctions:
            if j.joinedAt != frame.row:
                continue
            if j.joinedBy in state.hiddenCommits:
                continue
            assert j.joinedBy == frame.commit
            columnA, columnB = laneColumnsAB[arc.lane]
            ax = x + columnA * LANE_WIDTH
            bx = x + columnB * LANE_WIDTH
            path.moveTo(mx, middle)
            path.quadTo(bx, middle, bx, bottom)
            submitPath(path, arc.lane)

    # draw bullet point for this commit
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(getColor(commitLane) if oid != UC_FAKEID else UC_COLOR)
    painter.drawEllipse(QPoint(mx, middle), DOT_RADIUS, DOT_RADIUS)

    # we're done, clean up
    painter.restore()

    # add some padding to the right
    rect.setRight(rect.right() + LANE_WIDTH)

