from allqt import *
from itertools import zip_longest
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


def getLaneContinuity(state: RepoState, row: int, above: str, below: str):
    """
    Compute lane continuity.

    Returns a symbol representing the continuity/abridgment of the lane:

    ▄  Start of lane
    █
    █  Unbroken lane
    █
    ▼  Start of abridgment
    ▽  Abridged; column reserved above
    ~
    ~  Abridged; don't reserve a column
    ~
    △  Abridged; column reserved below
    ▲  End of abridgment
    █
    █
    █
    ▀  End of lane
       (space character) no lane occupancy
    """

    if not above and not below:
        return " "  # free lane
    elif not above and below:
        return "▄"  # lane begins below
    elif above and not below:
        return "▀"  # lane ends above

    targetHash = below
    targetMeta = state.commitLookup[targetHash]
    junctionHashes = [targetHash] + targetMeta.childHashes

    infinityish = len(state.commitSequence)
    jRowA = -1              # sequential index of nearest junction above
    jRowB = infinityish     # sequential index of nearest junction below

    # find nearest junctions above and below this row
    for jHash in junctionHashes:
        jRow = state.getCommitSequentialIndex(jHash)
        if jRow < row:  # above
            jRowA = max(jRow, jRowA)
        elif jRow > row:  # below
            jRowB = min(jRow, jRowB)
        elif jRow == row:
            return "█"  # edge case

    assert jRowA >= 0
    assert jRowB < infinityish
    assert jRowB > jRowA

    segmentLength = jRowB - jRowA

    if segmentLength <= ABRIDGMENT_THRESHOLD:
        return "█"  # unbroken lane
    elif row == jRowA+1:
        return "▼"  # start abridgment
    elif row == jRowA+2:
        return "▽"  # reserve column above
    elif row == jRowB-2:
        return "△"  # reserve column below
    elif row == jRowB-1:
        return "▲"  # end abridgment
    else:
        return "~"  # lane abridged


def flattenLanes(laneContinuity: list[str]) -> tuple[list[tuple[int, int]], int]:
    """
    Compute columns (horizontal positions) for each lane above and below this row.
    """

    laneColumnsAB = []

    if settings.prefs.graph_flattenLanes:
        # Flatten the lanes so there are no horizontal gaps in-between the lanes.
        ai, bi = -1, -1

        for c in laneContinuity:
            if c in " ~":
                pass
            elif c in "█▲▼":
                ai += 1
                bi += 1
            elif c in "▄△":
                bi += 1
            elif c in "▀▽":
                ai += 1
            else:
                assert False, F"unknown lane continuity type: {c}"
            laneColumnsAB.append( (ai, bi) )

        flatTotal = max(ai, bi)

    else:
        # Straightforward lane positions (lane column == lane ID)
        for i in range(len(laneContinuity)):
            laneColumnsAB.append( (i, i) )
        flatTotal = len(laneContinuity)

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

    # Get this commit's sequential index in the graph
    myRow = state.getCommitSequentialIndex(meta.hexsha)

    # Get lanes from neighbor above
    lanesA = []
    if myRow > 0:
        neighborA = state.commitSequence[myRow-1]
        lanesA = neighborA.graphFrame.lanesBelow

    # Zip target commits above and below for each lane
    lanesAB = list(zip_longest(lanesA, meta.graphFrame.lanesBelow))

    # Get the commit's lane ID
    commitLane = meta.graphFrame.commitLane

    # Compute lane continuity/abridgment info
    laneContinuity = []
    for i in range(len(lanesAB)):
        above, below = lanesAB[i]
        continuity = getLaneContinuity(state, myRow, above, below)
        laneContinuity.append(continuity)
    assert len(laneContinuity) == len(lanesAB)

    # Flatten the lanes so there are no horizontal gaps in-between the lanes (optional).
    # laneColumnsAB is a table of lanes to columns (horizontal positions).
    laneColumnsAB, numFlattenedColumns = flattenLanes(laneContinuity)

    # Get column (horizontal position) of commit bullet point.
    myColumn, numFlattenedColumns = getCommitBulletColumn(commitLane, numFlattenedColumns, laneColumnsAB)

    rect.setRight(x + numFlattenedColumns * LANE_WIDTH)
    mx = x + myColumn * LANE_WIDTH  # the screen X of this commit's bullet point

    # draw bullet point _outline_ for this commit, beneath everything else
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
        continuity = laneContinuity[i]

        if continuity in " ~△▽":  # skip free/fully-abridged lanes
            continue

        above, below = lanesAB[i]  # target commit above, target commit below
        columnA, columnB = laneColumnsAB[i]  # column above, column below
        dirA = sign(columnA - myColumn)  # position of columnA relative to myColumn (-1=left, 0=same, +1=right)
        dirB = sign(columnB - myColumn)  # position of columnB relative to myColumn (-1=left, 0=same, +1=right)
        ax = x + columnA * LANE_WIDTH
        bx = x + columnB * LANE_WIDTH

        pattern = Qt.SolidLine

        # Dotted line for abridged lane continued down
        if continuity == "▼":
            pattern = Qt.DotLine
            path.moveTo(ax, top)
            path.lineTo(ax, bottom)

        # Dotted line for abridged lane continued up
        elif continuity == "▲":
            pattern = Qt.DotLine
            path.moveTo(bx, bottom)
            path.lineTo(bx, top)

        else:
            assert continuity in "▄█▀"

            # Top to Bottom
            if above and above == below:
                path.moveTo(ax, top)
                path.cubicTo(ax, middle, bx, middle, bx, bottom)

            # Fork Up from Commit Bullet Point
            if above == meta.hexsha:
                # TODO: draw neater spline if i==commit lane
                path.moveTo(mx, middle)
                path.lineTo(ax-dirA*LANE_WIDTH, middle)
                path.quadTo(ax, middle, ax, top)

            # Fork Down from Commit Bullet Point
            if below in parentsRemaining and (below != parent0 or i == commitLane):
                path.moveTo(mx, middle)
                path.lineTo(bx-dirB*LANE_WIDTH, middle)
                path.quadTo(bx, middle, bx, bottom)
                parentsRemaining.remove(below)

        if not path.isEmpty():
            # white outline
            painter.setPen(QPen(outlineColor, LANE_THICKNESS + 2, Qt.SolidLine, Qt.FlatCap, Qt.BevelJoin))
            painter.drawPath(path)
            # actual color
            painter.setPen(QPen(getColor(i), LANE_THICKNESS, pattern, Qt.FlatCap, Qt.BevelJoin))
            painter.drawPath(path)
            # clear path for next iteration
            path.clear()

    # draw bullet point for this commit
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(getColor(commitLane))
    painter.drawEllipse(QPoint(mx, middle), DOT_RADIUS, DOT_RADIUS)

    # we're done, clean up
    painter.restore()

    # add some padding to the right
    rect.setRight(rect.right() + LANE_WIDTH)

