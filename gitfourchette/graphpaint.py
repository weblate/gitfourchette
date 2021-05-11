from allqt import *
from itertools import zip_longest
from repostate import CommitMetadata, RepoState
from util import sign
import colors
import settings


LANE_WIDTH = 10
LANE_THICKNESS = 2
DOT_RADIUS = 3


def getColor(laneID):
    return colors.rainbowBright[laneID % len(colors.rainbowBright)]


def flattenLanes(
        lanesAB: list[tuple[str, str]],
) -> tuple[list[tuple[int, int]], int]:
    # Compute columns (horizontal positions) for each lane above and below this row.
    laneColumnsAB = []
    if settings.prefs.graph_flattenLanes:
        # Flatten the lanes so there are no horizontal gaps in-between the lanes.
        ai, bi = -1, -1
        for above, below in lanesAB:
            if above: ai += 1
            if below: bi += 1
            laneColumnsAB.append( (ai, bi) )
        flatTotal = max(ai, bi)
    else:
        # Straightforward lane positions (lane column == lane ID)
        for i in range(len(lanesAB)):
            laneColumnsAB.append( (i, i) )
        flatTotal = len(lanesAB)

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
    if not meta or not meta.graphFrame:
        return

    painter.save()
    painter.setRenderHints(QPainter.Antialiasing, True)

    # Ensure all coordinates below are integers so our straight lines don't look blurry
    x = int(rect.left() + LANE_WIDTH // 2)
    top = int(rect.y())
    bottom = int(rect.y() + rect.height())  # Don't use rect.bottom(), which for historical reasons doesn't return what we want (see Qt docs)
    middle = (top + bottom) // 2

    MAX_LANES = settings.prefs.graph_maxLanes

    myRow = state.getCommitSequentialIndex(meta.hexsha)

    # Get lanes from neighbor above
    if myRow == 0:
        lanesA = []
    else:
        lanesA = state.commitSequence[myRow-1].graphFrame.lanesBelow

    # If there are too many lanes, cut off to MAX_LANES so the view stays somewhat readable.
    lanesA = lanesA[:MAX_LANES]
    lanesB = meta.graphFrame.lanesBelow[:MAX_LANES]

    lanesAB = list(zip_longest(lanesA, lanesB))
    commitLane = meta.graphFrame.commitLane

    # Flatten the lanes so there are no horizontal gaps in-between the lanes (optional).
    # laneColumnsAB is a table of lanes to columns (horizontal positions).
    laneColumnsAB, numFlattenedColumns = flattenLanes(lanesAB)

    # Get column (horizontal position) of commit bullet point.
    myLanePosition, numFlattenedColumns = getCommitBulletColumn(commitLane, numFlattenedColumns, laneColumnsAB)

    rect.setRight(x + numFlattenedColumns * LANE_WIDTH)
    mx = x + myLanePosition * LANE_WIDTH  # the screen X of this commit's bullet point

    # draw bullet point _outline_ for this commit, beneath everything else, if it's within the lanes that are shown
    if commitLane < MAX_LANES:
        painter.setPen(QPen(outlineColor, 2, Qt.SolidLine, Qt.FlatCap, Qt.BevelJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPoint(mx, middle), DOT_RADIUS, DOT_RADIUS)

    # parent info for Fork Down
    parentsRemaining = set(meta.parentHashes)
    parent0 = meta.parentHashes[0] if len(meta.parentHashes) > 0 else None

    path = QPainterPath()

    # draw lines
    # TODO: range(numLanesTotal-1,-1,-1) makes junctions more readable, but we should draw "straight" lines
    #  (unaffected by the commit) underneath junction lines
    for i in range(len(lanesAB)):
        commitAbove, commitBelow = lanesAB[i]
        columnAbove, columnBelow = laneColumnsAB[i]
        ax = x + columnAbove * LANE_WIDTH
        bx = x + columnBelow * LANE_WIDTH

        # position of lane `i` relative to MY_LANE: can be -1 (left), 0 (same), or +1 (right)
        direction = sign(i - commitLane)

        # Straight
        if commitAbove and commitAbove == commitBelow:
            path.moveTo(ax, top)
            path.cubicTo(ax,middle, bx,middle, bx,bottom)

        # Fork Up
        if commitAbove == meta.hexsha:
            path.moveTo(mx, middle)
            path.lineTo(ax-direction*LANE_WIDTH, middle)
            path.quadTo(ax,middle, ax,top)

        # Fork Down
        if commitBelow in parentsRemaining and (commitBelow != parent0 or i == commitLane):
            path.moveTo(mx, middle)
            path.lineTo(bx-direction*LANE_WIDTH, middle)
            path.quadTo(bx,middle, bx,bottom)
            parentsRemaining.remove(commitBelow)

        if not path.isEmpty():
            # white outline
            painter.setPen(QPen(outlineColor, LANE_THICKNESS + 2, Qt.SolidLine, Qt.FlatCap, Qt.BevelJoin))
            painter.drawPath(path)
            # actual color
            painter.setPen(QPen(getColor(i), LANE_THICKNESS, Qt.SolidLine, Qt.FlatCap, Qt.BevelJoin))
            painter.drawPath(path)
            path.clear()

    # show warning if we have too many lanes
    if len(meta.graphFrame.lanesBelow) > MAX_LANES:
        extraText = F"+{len(meta.graphFrame.lanesBelow) - MAX_LANES} lanes >>>  "
        painter.drawText(rect, Qt.AlignRight, extraText)

    # draw bullet point for this commit if it's within the lanes that are shown
    if commitLane < MAX_LANES:
        c = getColor(commitLane)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(c)
        painter.drawEllipse(QPoint(mx, middle), DOT_RADIUS, DOT_RADIUS)

    painter.restore()

    # add some padding to the right
    rect.setRight(rect.right() + LANE_WIDTH)

