from allqt import *
from itertools import zip_longest
from graph import Frame, Graph
from repostate import CommitMetadata, RepoState
from util import sign
import colors
import settings


LANE_WIDTH = 10
LANE_THICKNESS = 2
DOT_RADIUS = 3
ABRIDGMENT_THRESHOLD = 50


def getColor(laneID):
    return colors.rainbowBright[laneID % len(colors.rainbowBright)]


def flattenLanes(frame: Frame) -> tuple[list[tuple[int, int]], int]:
    """
    Compute columns (horizontal positions) for each lane above and below this row.
    """

    laneColumnsAB = []

    if settings.prefs.graph_flattenLanes:
        # Flatten the lanes so there are no horizontal gaps in-between the lanes.
        ai, bi = -1, -1

        for cl, ol in zip_longest(frame.staleArcs, frame.openArcs):
            if ol:
                bi += 1
                if ol.openedAt < frame.row:
                    ai += 1
            if cl:
                ai += 1
            laneColumnsAB.append( (ai, bi) )

        flatTotal = max(ai, bi)

    else:
        # Straightforward lane positions (lane column == lane ID)
        for i, (cl, ol) in enumerate(zip_longest(frame.staleArcs, frame.openArcs)):
            laneColumnsAB.append( (i, i) )
        flatTotal = len(laneColumnsAB)#len(laneContinuity)

    return laneColumnsAB, flatTotal


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
        meta: CommitMetadata,
        painter: QPainter,
        rect: QRect,
        outlineColor: QColor
):
    if not meta or not state.graph:#meta.graphFrame:
        return

    painter.save()
    painter.setRenderHints(QPainter.Antialiasing, True)

    # Ensure all coordinates below are integers so our straight lines don't look blurry
    x = int(rect.left() + LANE_WIDTH // 2)
    top = int(rect.y())
    bottom = int(rect.y() + rect.height())  # Don't use rect.bottom(), which for historical reasons doesn't return what we want (see Qt docs)
    middle = (top + bottom) // 2

    # Get this commit's sequential index in the graph
    myRow = state.getCommitSequentialIndex(meta.hexsha)

    # Get graph frame for this row
    frame = state.graph.startPlayback(myRow).copyCleanFrame()

    # Get the commit's lane ID
    commitLane = frame.getHomeLaneForCommit()

    # Flatten the lanes so there are no horizontal gaps in-between the lanes (optional).
    # laneColumnsAB is a table of lanes to columns (horizontal positions).
    laneColumnsAB, numFlattenedColumns = flattenLanes(frame)#laneContinuity)

    # Get column (horizontal position) of commit bullet point.
    myColumn, numFlattenedColumns = getCommitBulletColumn(commitLane, numFlattenedColumns, laneColumnsAB)

    rect.setRight(x + numFlattenedColumns * LANE_WIDTH)
    mx = x + myColumn * LANE_WIDTH  # the screen X of this commit's bullet point

    # draw bullet point _outline_ for this commit, beneath everything else
    painter.setPen(QPen(outlineColor, 2, Qt.SolidLine, Qt.FlatCap, Qt.BevelJoin))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(QPoint(mx, middle), DOT_RADIUS, DOT_RADIUS)

    path = QPainterPath()

    def submitPath(path: QPainterPath, column):
        if not path.isEmpty():
            # white outline
            painter.setPen(QPen(outlineColor, LANE_THICKNESS + 2, Qt.SolidLine, Qt.FlatCap, Qt.BevelJoin))
            painter.drawPath(path)
            # actual color
            painter.setPen(QPen(getColor(column), LANE_THICKNESS, Qt.SolidLine, Qt.FlatCap, Qt.BevelJoin))
            painter.drawPath(path)
            # clear path for next iteration
            path.clear()

    for link in frame.getArcsPassingByCommit():
        columnA, columnB = laneColumnsAB[link.lane]  # column above, column below
        ax = x + columnA * LANE_WIDTH
        bx = x + columnB * LANE_WIDTH
        path.moveTo(ax, top)
        path.cubicTo(ax, middle, bx, middle, bx, bottom)
        submitPath(path, link.lane)

    for link in reversed(list(frame.getArcsClosedByCommit())):
        columnA, _ = laneColumnsAB[link.lane]  # column above, column below
        ax = x + columnA * LANE_WIDTH
        # Fork Up from Commit Bullet Point
        path.moveTo(mx, middle)
        path.quadTo(ax, middle, ax, top)
        submitPath(path, link.lane)

    for link in reversed(list(frame.getArcsOpenedByCommit())):
        _, columnB = laneColumnsAB[link.lane]  # column above, column below
        bx = x + columnB * LANE_WIDTH
        # Fork Down from Commit Bullet Point
        path.moveTo(mx, middle)
        #path.lineTo(bx-dirB*LANE_WIDTH, middle)
        path.quadTo(bx, middle, bx, bottom)
        submitPath(path, link.lane)

    for link in frame.getArcsPassingByCommit():
        for j in link.junctions:
            if j.joinedAt != frame.row:
                continue
            assert j.joinedBy == frame.commit
            columnA, columnB = laneColumnsAB[link.lane]
            ax = x + columnA * LANE_WIDTH
            bx = x + columnB * LANE_WIDTH
            path.moveTo(mx, middle)
            path.quadTo(bx, middle, bx, bottom)
            submitPath(path, link.lane)

    # draw bullet point for this commit
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(getColor(commitLane))
    painter.drawEllipse(QPoint(mx, middle), DOT_RADIUS, DOT_RADIUS)

    # we're done, clean up
    painter.restore()

    # add some padding to the right
    rect.setRight(rect.right() + LANE_WIDTH)

