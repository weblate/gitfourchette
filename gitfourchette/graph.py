from __future__ import annotations

import bisect
from contextlib import suppress
import itertools
import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import ClassVar, Iterable, Iterator

from gitfourchette.porcelain import Oid as _RealOidType
from gitfourchette.settings import DEVDEBUG
from gitfourchette.toolbox import *

logger = logging.getLogger(__name__)

KF_INTERVAL = 5000
"""
Interval (in number of commits) at which keyframes are saved while preparing
the graph.

The bigger the interval...:
- faster initial loading of the repo & less memory usage;
- but slower random access to any point of the graph.
"""

ABRIDGMENT_THRESHOLD = 25

DEAD_VALUE = "!DEAD"

Oid = _RealOidType | str


@dataclass(frozen=True)
class BatchRow:
    """
    For a row in the Graph, BatchRow keeps track of the row's batch number
    and position within the batch.

    When a repo is refreshed, new commits may appear at the top of the graph.
    This may push existing rows down, away from the top of the graph.

    Recomputing row numbers for the entire graph becomes costly if it contains
    tens of thousands of commits.

    Instead, we keep track of batches of rows inserted into the graph at each
    refresh. We adjust a single offset value for each batch.
    """

    b: int = -1
    "Batch number (look up its global offset in BatchManager)"

    y: int = -1
    "Position of this row relative to its batch"

    class BatchManager:
        """
        Manages row batch offsets.

        A single BatchManager is shared by all repositories opened throughout
        the lifespan of the app.
        """

        globalOffsets: ClassVar[list[int]] = []
        freeBatchNos: ClassVar[list[int]] = []

        @classmethod
        def reserveNewBatch(cls):
            if cls.freeBatchNos:
                batchNo = cls.freeBatchNos.pop()
                cls.globalOffsets[batchNo] = 0
            else:
                cls.globalOffsets.append(0)
                batchNo = len(cls.globalOffsets) - 1

            return batchNo

        @classmethod
        def freeBatch(cls, batchNo: int):
            cls.globalOffsets[batchNo] = -1
            cls.freeBatchNos.append(batchNo)

            # Compact end of list
            while cls.globalOffsets and cls.globalOffsets[-1] == -1:
                with suppress(ValueError):
                    cls.freeBatchNos.remove(len(cls.globalOffsets) - 1)
                cls.globalOffsets.pop()

        @classmethod
        def shiftBatches(cls, shift: int, batchNos: Iterable[int]):
            for b in batchNos:
                cls.globalOffsets[b] += shift

    def isValid(self):
        """
        A BatchRow is considered valid if it is part of a valid batch, it has a
        positive offset in the batch, and it resolves to a positive int.
        """
        return self.b >= 0 and self.y >= 0 and int(self) >= 0

    def __repr__(self):
        offset = -1 if self.b < 0 else BatchRow.BatchManager.globalOffsets[self.b]
        return f"{int(self)} (b{self.b}r{self.y}+{offset})"

    def __str__(self):
        return str(int(self))

    def __int__(self) -> int:
        """Any BatchRow is convertible to int, giving a global row index.
        Note that the int value of any given BatchRow may change over time
        as the graph gets spliced."""
        if self.b < 0:
            return -1
        return BatchRow.BatchManager.globalOffsets[self.b] + self.y

    # -------------------------------------------------------------------------
    # Arithmetics

    def __add__(self, other: BatchRow | int) -> int:
        return int(self) + int(other)

    def __sub__(self, other: BatchRow | int) -> int:
        return int(self) - int(other)

    def __mod__(self, other: BatchRow | int) -> int:
        return int(self) % int(other)

    def __rmod__(self, other: BatchRow | int) -> int:
        return int(other) % int(self)

    # -------------------------------------------------------------------------
    # Comparisons
    # (BatchRows must be comparable so we can use bisect.)

    def __le__(self, other: BatchRow | int):
        return int(self) <= int(other)

    def __lt__(self, other: BatchRow | int):
        return int(self) < int(other)

    def __ge__(self, other: BatchRow | int):
        return int(self) >= int(other)

    def __gt__(self, other: BatchRow | int):
        return int(self) > int(other)

    def __eq__(self, other: BatchRow | int):
        return int(self) == int(other)


BATCHROW_UNDEF = BatchRow(-1, -1)
"Use this special BatchRow as a placeholder for a row position that is yet to be determined."


@dataclass
class ChainHandle:
    """ Object shared by arcs on the same chain. """
    _t: BatchRow = BATCHROW_UNDEF
    _b: BatchRow = BATCHROW_UNDEF
    alias: ChainHandle | None = None

    def isValid(self):
        # It's OK for bottomRow to be dangling, but not topRow.
        return self.topRow.isValid()

    def __repr__(self):
        tr = int(self.topRow)
        br = int(self.bottomRow)
        return f"Chain({tr}\u2192{br})"

    def resolve(self):
        """ Return non-aliased ChainHandle """

        if self.alias is None:
            return self

        if self.alias.alias is not None:
            # Flatten aliases
            frontier = [self, self.alias]
            root = frontier[-1]
            while True:
                root = root.alias
                if root.alias is None:
                    break
                frontier.append(root)
            for ch in frontier:
                ch.alias = root
            if DEVDEBUG:
                assert root.alias is None
                assert root not in frontier
                assert root is self.alias

        return self.alias

    @property
    def topRow(self) -> BatchRow:
        return self.resolve()._t

    @property
    def bottomRow(self) -> BatchRow:
        return self.resolve()._b

    @bottomRow.setter
    def bottomRow(self, value):
        self._b = value
        assert self.alias is None, "Cannot modify row in aliased ChainHandle"

    def setAliasOf(self, master: ChainHandle):
        if self.alias is not None:
            self.alias.setAliasOf(master)

        self.alias = master
        self._t = BATCHROW_UNDEF
        self._b = BATCHROW_UNDEF


@dataclass
class ArcJunction:
    """ Represents the merging of an Arc into another Arc. """

    joinedAt: BatchRow
    "Row number in which this junction occurs"

    joinedBy: Oid
    "Hash of the joining arc's opening commit"

    def __lt__(self, other: ArcJunction):
        """
        Calling sorted() on a list of ArcJunctions will sort them by `joinedAt` (row numbers).
        """
        return self.joinedAt < other.joinedAt


@dataclass
class Arc:
    """ An arc connects two commits in the graph.

    Commits appear before their parents in the commit sequence.
    When processing the commit sequence, we "open" a new arc when
    encountering a new commit. The arc stays "open" until we've found
    the commit's parent in the sequence, at which point we "close" it.

    Other arcs may merge into an open arc via an ArcJunction.
    """

    openedAt: BatchRow
    "Row number in which this arc was opened"

    closedAt: BatchRow
    "Row number in which this arc was closed (may be BATCHROW_UNDEF until resolved)"

    chain: ChainHandle
    "Row number of the tip of the arc chain (topmost commit in branch)"

    lane: int
    "Lane assigned to this arc"

    openedBy: Oid
    "Hash of the opening commit (in git parlance, the child commit)"

    closedBy: Oid
    "Hash of the closing commit (in git parlance, the parent commit)"

    junctions: list[ArcJunction]
    "Other arcs merging into this arc"

    nextArc: Arc | None = None
    "Next node in the arc linked list"

    def __repr__(self):
        oa = int(self.openedAt)
        ca = int(self.closedAt)
        ob = str(self.openedBy)[:5]
        cb = str(self.closedBy)[:5]
        dangling = "?" if not self.closedAt.isValid() else ""
        return f"Arc({self.chain} {ob}\u2192{cb}{dangling} {oa}\u2192{ca})"

    def length(self):
        assert type(self.openedAt) == BatchRow
        assert type(self.closedAt) == BatchRow
        return int(self.closedAt) - int(self.openedAt)

    def __next__(self):
        return self.nextArc

    def __iter__(self) -> Iterator[Arc]:
        arc = self
        while arc:
            yield arc
            assert arc.nextArc != arc, "self-referencing arc!"
            arc = arc.nextArc

    def getNumberOfArcsFromHere(self):
        n = 0
        for _ in self:
            n += 1
        return n

    def isParentlessCommitBogusArc(self):
        return self.openedBy == self.closedBy

    def connectsHiddenCommit(self, hiddenCommits: set):
        return self.openedBy in hiddenCommits or self.closedBy in hiddenCommits

    def isIndependentOfRowsAbove(self, row: int):
        """ Return True if this arc is entirely independent of row numbers lower than `row`. """
        return self.openedAt >= row and self.closedAt >= row

    def isStale(self, row: int):
        """
        Return True if this arc is considered stale at a given row in the graph.
        An arc is stale at row 'R' if it is closed above 'R',
        or if it is a ParentlessCommitBogusArc appearing at or above 'R',
        or if it is dangling (its closedAt row hasn't been resolved yet).
        """
        ca = int(self.closedAt)
        return (0 <= ca < row) or (0 <= ca == self.openedAt <= row)


@dataclass
class Frame:
    """ A frame is a slice of the graph at a given row. """

    row: BatchRow
    commit: Oid
    solvedArcs: list[Arc | None]  # Arcs that have resolved their parent commit
    openArcs: list[Arc | None]  # Arcs that have not resolved their parent commit yet
    lastArc: Arc

    def getArcsClosedByCommit(self):
        return (arc for arc in self.solvedArcs if arc and arc.closedAt == self.row)

    def getArcsOpenedByCommit(self):
        return (arc for arc in self.openArcs if arc and arc.openedAt == self.row)

    def getArcsPassingByCommit(self):
        return (arc for arc in self.openArcs if arc and arc.openedAt != self.row)

    def getHomeArcForCommit(self) -> Arc:
        leftmostClosed = next(self.getArcsClosedByCommit(), None)
        leftmostOpened = next(self.getArcsOpenedByCommit(), None)
        if leftmostOpened and leftmostClosed:
            return max(leftmostClosed, leftmostOpened, key=lambda a: a.lane)
        elif leftmostClosed:
            return leftmostClosed
        elif leftmostOpened:
            return leftmostOpened
        else:
            # It's a parentless + childless commit.
            # Implementation detail: for parentless commits, we create a bogus arc
            # as the "last" arc in the frame; we can get the lane from this bogus arc.
            assert self.lastArc.isParentlessCommitBogusArc()
            assert self.lastArc.openedBy == self.commit
            return self.lastArc

    def getHomeLaneForCommit(self) -> int:
        return self.getHomeArcForCommit().lane

    def getHomeChainForCommit(self) -> ChainHandle:
        return self.getHomeArcForCommit().chain

    def sealCopy(self) -> Frame:
        """
        Generated frames must be "sealed off" to make them suitable
        for rendering or for use as keyframes.
        """
        solvedArcsCopy = self.solvedArcs.copy()
        openArcsCopy = self.openArcs.copy()

        # Move arcs that just got closed to solved list
        for lane, arc in enumerate(openArcsCopy):
            if arc and 0 <= arc.closedAt <= self.row:
                openArcsCopy[lane] = None

                # For parentless commits, prevent bogus auto-closing arcs
                # from overwriting legitimate closed arcs.
                if not arc.isParentlessCommitBogusArc():
                    self.reserveArcListCapacity(solvedArcsCopy, lane+1)
                    solvedArcsCopy[lane] = arc

        # Remove stale closed arcs and trim "Nones" off end of list
        self.cleanUpArcList(openArcsCopy, self.row, alsoTrimBack=True)
        self.cleanUpArcList(solvedArcsCopy, self.row, alsoTrimBack=True)

        # In debug mode, make sure none of the arcs are dangling
        assert all(arc is None or arc.openedBy != DEAD_VALUE for arc in openArcsCopy)
        assert all(arc is None or arc.openedBy != DEAD_VALUE for arc in solvedArcsCopy)
        assert all(arc is None or arc.chain.isValid() for arc in openArcsCopy)
        assert all(arc is None or arc.chain.isValid() for arc in solvedArcsCopy)

        return Frame(self.row, self.commit, solvedArcsCopy, openArcsCopy, self.lastArc)

    @staticmethod
    def reserveArcListCapacity(theList, newLength):
        if len(theList) >= newLength:
            return
        for i in range(newLength - len(theList)):
            theList.append(None)

    @staticmethod
    def cleanUpArcList(theList: list[Arc|None], olderThanRow: BatchRow, alsoTrimBack: bool = True):
        # Remove references to arcs that were closed earlier than `olderThanRow`
        for j, arc in enumerate(theList):
            if arc and 0 <= arc.closedAt < olderThanRow:
                theList[j] = None

        # Cull None items at the end of the list
        if alsoTrimBack:
            while theList and not theList[-1]:
                del theList[-1]

        return theList

    def flattenLanes(self, hiddenCommits: set[Oid]) -> tuple[list[tuple[int, int]], int]:
        """Flatten the lanes so there are no unused columns in-between the lanes."""

        row = self.row

        # Filter arcs

        def keepArc(a: Arc):
            return a and not a.connectsHiddenCommit(hiddenCommits)

        arcsAbove = itertools.chain(filter(keepArc, self.solvedArcs),
                                    (a for a in self.openArcs if keepArc(a) and a.openedAt < row))
        arcsBelow = filter(keepArc, self.openArcs)

        # Sort arcs by Chain Birth Row

        def sortArc(a: Arc):
            return int(a.chain.topRow) * 1000 + a.lane

        arcsAbove = sorted(arcsAbove, key=sortArc, reverse=True)
        arcsBelow = sorted(arcsBelow, key=sortArc, reverse=True)

        # Assign columns to all lanes used by arcs above and below

        N = max(len(self.solvedArcs), len(self.openArcs))
        mapAbove = [-1] * N
        mapBelow = [-1] * N

        column = -1
        while arcsAbove or arcsBelow:
            column += 1

            if arcsAbove:
                a = arcsAbove.pop()
                mapAbove[a.lane] = column

            if arcsBelow:
                a = arcsBelow.pop()
                mapBelow[a.lane] = column

        return list(zip(mapAbove, mapBelow)), column

    def textDiagram(self):
        COLUMN_WIDTH = 2

        def getx(lane):
            assert lane >= 0
            assert lane < maxLanes
            return lane * COLUMN_WIDTH

        homeArc = self.getHomeArcForCommit()
        homeLane = homeArc.lane
        homeChain = homeArc.chain

        maxLanes = max(len(self.openArcs), len(self.solvedArcs)) + 1

        gridHi = [" "] * (maxLanes * COLUMN_WIDTH + 4)
        gridLo = [" "] * (maxLanes * COLUMN_WIDTH + 4)
        for pl in self.getArcsPassingByCommit():
            if pl.length() > ABRIDGMENT_THRESHOLD:
                gridHi[getx(pl.lane)] = "┊"  # TODO: Depending on junctions, we may or may not want to abridge
                gridLo[getx(pl.lane)] = "┊"
            else:
                gridHi[getx(pl.lane)] = "│"
                gridLo[getx(pl.lane)] = "│"

        closed = list(self.getArcsClosedByCommit())
        opened = list(self.getArcsOpenedByCommit())
        passing = list(self.getArcsPassingByCommit())

        def hline(scanline, fromCol, toCol):
            lcol = min(fromCol, toCol)
            rcol = max(fromCol, toCol)
            for i in range(getx(lcol), getx(rcol) + 1):
                scanline[i] = "─"

        if closed:
            leftmostClosedLane = min([cl.lane for cl in closed])
            rightmostClosedLane = max([cl.lane for cl in closed])
            hline(gridHi, leftmostClosedLane, rightmostClosedLane)
            for cl in closed:
                if cl.lane == homeLane:
                    gridHi[getx(cl.lane)] = "│"

        if opened:
            leftmostOpenedLane = min([l.lane for l in opened])
            rightmostOpenedLane = max([l.lane for l in opened])
            hline(gridLo, leftmostOpenedLane, rightmostOpenedLane)
            for ol in opened:
                if ol.lane == homeLane:
                    gridLo[getx(ol.lane)] = "│"

        for cl in closed:
            if cl.lane > homeLane:
                gridHi[getx(cl.lane)] = "╯"
            elif cl.lane < homeLane:
                gridHi[getx(cl.lane)] = "╰"

        for ol in opened:
            if ol.lane > homeLane:
                gridLo[getx(ol.lane)] = "╮"
            elif ol.lane < homeLane:
                gridLo[getx(ol.lane)] = "╭"

        junctionExplainer = ""
        for pl in passing:
            assert pl.junctions == sorted(pl.junctions), "Junction list is supposed to be sorted!"
            for junction in pl.junctions:
                if junction.joinedAt == self.row:
                    assert junction.joinedBy == self.commit, F"junction commit {junction.joinedBy} != frame commit {self.commit}  at junction row {junction.joinedAt}"
                    hline(gridLo, homeLane, pl.lane)
                    if homeLane > pl.lane:
                        gridLo[getx(pl.lane)] = "╭"
                        gridLo[getx(homeLane)] = "╯"
                    elif homeLane < pl.lane:
                        gridLo[getx(pl.lane)] = "╮"
                        gridLo[getx(homeLane)] = "╰"
                    else:
                        assert False, "junction plugged into passing arc that's on my homeLane?"
                    junctionExplainer += F"JunctionOn\"{pl}\":{homeLane}[{junction.joinedBy[:4]}]->{pl.lane};"

        if not opened and not closed:
            gridHi[getx(homeLane)] = "╳"  # "━"
        elif not opened:
            ## TODO: this is drawn for some orphan commits!
            # if len(closed) == 1 and closed[0].closedAt == closed[0].openedAt:
            #    gridHi[getx(homeLane)] = "?╳"
            # else:
            #    gridHi[getx(homeLane)] = "┷"
            gridHi[getx(homeLane)] = "┷"
        elif not closed:
            gridHi[getx(homeLane)] = "┯"
        else:
            gridHi[getx(homeLane)] = "┿"

        gridHiStr = ''.join(gridHi)
        gridLoStr = ''.join(gridLo)

        text = ""
        text += F"{int(self.row):<4} {int(homeChain.topRow):<4} {str(self.commit)[:4]:>4} {gridHiStr}\n"
        if any(c in gridLoStr for c in "╭╮╰╯"):
            text += F"{' ' * 14} {gridLoStr} {junctionExplainer}\n"
        return text


class GeneratorState(Frame):
    freeLanes: list[int]
    parentLookup: defaultdict[Oid, list[Arc]]  # all lanes
    peakArcCount: int
    batchNo: int

    def __init__(self, startArcSentinel: Arc):
        super().__init__(row=BATCHROW_UNDEF, commit="",
                         solvedArcs=[], openArcs=[], lastArc=startArcSentinel)
        self.freeLanes = []
        self.parentLookup = defaultdict(list)
        self.peakArcCount = 0
        self.batchNo = BatchRow.BatchManager.reserveNewBatch()

    def newCommit(self, me: Oid, myParents: list[Oid]):
        """Create arcs for a new commit row."""

        row = BatchRow(b=self.batchNo, y=self.row.y + 1)
        self.row = row
        self.commit = me

        hasParents = len(myParents) > 0

        # Resolve arcs that my child commits have opened higher up in the graph,
        # waiting for me to appear in the commit sequence so I can close them.
        myOpenArcs = self.parentLookup.get(me)
        myHomeLane = -1
        handOffHomeLane = False
        if not myOpenArcs:
            # Nobody was looking for me, so I'm the tip of a new branch
            myHomeChain = ChainHandle(row, BATCHROW_UNDEF)
        else:
            myMainOpenArc = min(myOpenArcs, key=lambda a: a.lane)
            myHomeLane = myMainOpenArc.lane
            myHomeChain = myMainOpenArc.chain
            assert myHomeChain.isValid()
            for arc in myOpenArcs:
                # Close off open arcs
                assert arc.closedBy == me
                assert arc.closedAt == BATCHROW_UNDEF
                assert arc.chain.bottomRow == BATCHROW_UNDEF
                arc.closedAt = row
                self.solvedArcs[arc.lane] = arc
                self.openArcs[arc.lane] = None  # Free up the lane below
                if hasParents and arc.lane == myHomeLane:
                    handOffHomeLane = True
                else:
                    bisect.insort(self.freeLanes, arc.lane)
                    # Close off chain
                    arc.chain.bottomRow = row
            del self.parentLookup[me]

            """ 
            # Compact null arcs at right of graph
            if not allocLanesInGaps:
                for _ in range(len(self.openArcs)-1, myHomeLane, -1):
                    if self.openArcs[-1] is not None:
                        break
                    self.openArcs.pop()
                    self.solvedArcs.pop()
            """

        sawFirstParent = False
        for parent in myParents:
            # See if there's already an arc that is looking for any of my parents BEYOND PARENT ZERO.
            # If so, make a junction on that arc.
            if sawFirstParent:
                arcsOfParent = self.parentLookup.get(parent)
                if arcsOfParent:
                    arc = min(arcsOfParent, key=lambda a: a.lane)
                    assert arc.closedBy == parent
                    assert arc.closedAt == BATCHROW_UNDEF
                    arc.junctions.append(ArcJunction(joinedAt=row, joinedBy=me))
                    continue

            # We didn't make a junction, so open up a new arc on a free lane.
            # Get a free lane.
            if not sawFirstParent and myHomeLane >= 0:
                assert handOffHomeLane
                freeLane = myHomeLane
                handOffHomeLane = False
            elif not self.freeLanes:
                # Allocate new lane on the right
                freeLane = len(self.openArcs)
                self.openArcs.append(None)  # Reserve the lane
                self.solvedArcs.append(None)  # Reserve the lane
            else:
                # Pick leftmost free lane
                freeLane = self.freeLanes.pop(0)

            if not sawFirstParent:
                # Hand off my chain
                parentChain = myHomeChain
            else:
                # Branch out new chain downward
                parentChain = ChainHandle(row, BATCHROW_UNDEF)
            assert parentChain.bottomRow == BATCHROW_UNDEF

            # Make arc from this commit to its parent
            newArc = Arc(lane=freeLane, chain=parentChain,
                         openedAt=row, closedAt=BATCHROW_UNDEF,
                         openedBy=me, closedBy=parent, junctions=[])
            self.openArcs[freeLane] = newArc
            self.parentLookup[parent].append(newArc)
            self.lastArc.nextArc = newArc
            self.lastArc = newArc

            sawFirstParent = True

        # Parentless commit: we'll insert a bogus arc so playback doesn't need the commit sequence.
        # This is just to keep the big linked list of arcs flowing.
        # Do NOT put it in solved or open arcs! This would interfere with detection of arcs that the commit
        # actually closes or opens.
        if not sawFirstParent:
            if myHomeLane < 0:
                # Edge case: the commit is BOTH childless AND parentless.
                # Put the commit in a free lane, but do NOT reserve the lane.
                if not self.freeLanes:
                    myHomeLane = len(self.openArcs)
                else:
                    myHomeLane = self.freeLanes[0]  # PEEK only! do not pop!

                # Close off home chain
                myHomeChain.bottomRow = row

            assert myHomeChain.bottomRow.isValid(), "parentless commit's home chain shouldn't be dangling at bottom"

            newArc = Arc(lane=myHomeLane, chain=myHomeChain,
                         openedAt=row, closedAt=row,
                         openedBy=me, closedBy=me, junctions=[])
            self.lastArc.nextArc = newArc
            self.lastArc = newArc
            assert newArc.isParentlessCommitBogusArc()

        assert not handOffHomeLane
        assert myHomeChain.topRow.isValid()
        assert len(self.openArcs) == len(self.solvedArcs)

        # Keep track of peak arc count for statistics
        self.peakArcCount = max(self.peakArcCount, len(self.openArcs))

    def isDangling(self):
        return len(self.parentLookup) > 0


class PlaybackState(Frame):
    def __init__(self, keyframe: Frame):
        super().__init__(
            row=keyframe.row,
            commit=keyframe.commit,
            solvedArcs=[],
            openArcs=[],
            lastArc=keyframe.lastArc)

        self.solvedArcs = keyframe.solvedArcs.copy()
        self.openArcs = keyframe.openArcs.copy()
        self.callingNextWillAdvanceFrame = True
        self.seenCommits = set()

    def advanceToNextRow(self):
        if not self.callingNextWillAdvanceFrame:
            self.callingNextWillAdvanceFrame = True
            return

        # Put commit from previous iteration into set of previously-seen commits
        if self.commit:
            self.seenCommits.add(self.commit)

        goalFound = False
        goalRow = BATCHROW_UNDEF
        goalCommit = ""

        while self.lastArc.nextArc:
            arc: Arc = self.lastArc.nextArc

            if not goalFound and arc.openedAt > self.row:
                # The goal row is determined by the first arc opened at a row greater than the player's current row.
                goalFound = True
                goalRow = arc.openedAt
                goalCommit = arc.openedBy
            elif goalFound and arc.openedAt > goalRow:
                # If we went past the goal row, we have seen all arcs opened at the goal row. Stop.
                break
            else:
                # Keep iterating on arcs in the goal row. Gather them in a frame.
                pass

            self.reserveArcListCapacity(self.solvedArcs, arc.lane + 1)
            self.reserveArcListCapacity(self.openArcs, arc.lane + 1)

            self.solvedArcs[arc.lane] = self.openArcs[arc.lane]  # move any open arc to "just closed"
            self.openArcs[arc.lane] = arc
            self.lastArc = arc

        if not goalCommit:
            raise StopIteration()

        assert self.row < goalRow
        self.row = goalRow
        self.commit = goalCommit

        assert isinstance(self.row, BatchRow)

    def advanceToCommit(self, commit: Oid):
        """
        Advances playback until a specific commit hash is found.
        Raises StopIteration if the commit wasn't found.
        """
        justSeenCommits = set()
        if self.commit == commit:
            self.callingNextWillAdvanceFrame = True
            justSeenCommits.add(self.commit)
        else:
            while self.commit != commit:
                self.advanceToNextRow()
                justSeenCommits.add(self.commit)
        return justSeenCommits

    def __iter__(self):
        return self

    def __next__(self):
        self.advanceToNextRow()
        return self


class Graph:
    keyframes: list[Frame]
    keyframeRows: list[BatchRow]

    startArc: Arc
    """
    Start sentinel of the linked list of Arcs. Guaranteed to never be None.
    Use startArc.nextArc to get to the first actual arc.
    """

    commitRows: dict[Oid, BatchRow]
    ownBatches: list[int]

    volatilePlayer: PlaybackState | None

    def __init__(self):
        self.keyframes = []
        self.keyframeRows = []
        self.commitRows = {}
        self.startArc = Arc(
            openedAt=BATCHROW_UNDEF,
            closedAt=BATCHROW_UNDEF,
            chain=ChainHandle(BATCHROW_UNDEF, BATCHROW_UNDEF),
            lane=-1,
            openedBy="!TOP",
            closedBy="!BOTTOM",
            junctions=[],
            nextArc=None)
        self.ownBatches = []
        self.volatilePlayer = None

    def __del__(self):
        self.freeOwnBatches()

    def freeOwnBatches(self):
        for b in self.ownBatches:
            BatchRow.BatchManager.freeBatch(b)
        self.ownBatches = []

    def shallowCopyFrom(self, source: Graph):
        assert not set(self.ownBatches).intersection(set(source.ownBatches))

        # Free up owned batches
        self.freeOwnBatches()

        self.keyframes = source.keyframes
        self.keyframeRows = source.keyframeRows
        self.startArc = source.startArc
        self.commitRows = source.commitRows
        self.ownBatches = source.ownBatches

        source.ownBatches = []

        source.volatilePlayer = None
        self.volatilePlayer = None

    def isEmpty(self):
        return self.startArc.nextArc is None

    def getCommitRow(self, oid: Oid):
        return int(self.commitRows[oid])

    def generateFullSequence(self, sequence: list[Oid], parentsOf: dict[Oid, list[Oid]],
                             keyframeInterval=KF_INTERVAL) -> GeneratorState:
        generator = GeneratorState(self.startArc)

        self.ownBatches.append(generator.batchNo)

        for commit in sequence:
            generator.newCommit(commit, parentsOf[commit])

            self.commitRows[commit] = generator.row

            # Save keyframes at regular intervals for faster random access.
            if int(generator.row) % keyframeInterval == 0:
                self.saveKeyframe(generator)

        return generator

    def spliceTop(self, oldHeads: set[Oid], newHeads: set[Oid],
                  sequence: list[Oid], parentsOf: dict[Oid, list[Oid]],
                  keyframeInterval: int = KF_INTERVAL
                  ) -> GraphSplicer:
        splicer = GraphSplicer(self, oldHeads, newHeads)
        for commit in sequence:
            splicer.spliceNewCommit(commit, parentsOf[commit], keyframeInterval)
            if not splicer.keepGoing:
                break
        splicer.finish()
        return splicer

    def saveKeyframe(self, frame: Frame) -> int:
        assert len(self.keyframes) == len(self.keyframeRows)

        kfID = bisect.bisect_left(self.keyframeRows, frame.row)
        if kfID < len(self.keyframes) and self.keyframes[kfID].row == frame.row:
            logger.info(f"Not overwriting existing keyframe {kfID}")
            assert self.keyframes[kfID] == frame.sealCopy()
        else:
            kf = frame.sealCopy()
            self.keyframes.insert(kfID, kf)
            self.keyframeRows.insert(kfID, frame.row)
        return kfID

    def getBestKeyframeID(self, row: int) -> int:
        """
        Attempts to find a keyframe closest to `row` in the frame sequence.
        If an adequate keyframe is found, return its index into the keyframes list; otherwise, return -1.
        Note that the returned value is an **index into the list of keyframes**; it is NOT a frame row number.

        If a valid keyframe was found, its row is guaranteed to be lower or equal to `row`.
        This function never returns a keyframe located at a greater row than `row`.

        If the keyframe occurs before the desired `row`, you can create a PlaybackState from that keyframe
        and iterate the PlaybackState until it reaches the desired row.
        """
        assert row >= 0
        assert len(self.keyframes) == len(self.keyframeRows)

        bestKeyframeID = bisect.bisect_right(self.keyframeRows, row) - 1
        if bestKeyframeID < 0:
            return -1

        bestKeyframeRow = self.keyframeRows[bestKeyframeID]
        assert 0 <= bestKeyframeRow <= row

        return bestKeyframeID

    def startGenerator(self) -> GeneratorState:
        assert self.isEmpty(), "cannot regenerate an existing graph!"
        generator = GeneratorState(self.startArc)
        self.ownBatches.append(generator.batchNo)
        return generator

    def startPlayback(self, goalRow: int = 0, oneOff: bool = False) -> PlaybackState:
        kfID = self.getBestKeyframeID(goalRow)
        if kfID >= 0:
            kf = self.keyframes[kfID]
        else:
            kf = self.initialKeyframe()

        if oneOff and self.volatilePlayer and goalRow >= self.volatilePlayer.row >= kf.row:
            player = self.volatilePlayer
        else:
            player = PlaybackState(kf)

        # Position playback context on target row
        try:
            volatileKeyframeCounter = 1
            assert player.row <= goalRow, f"{player.row} {goalRow}"
            while player.row < goalRow:
                player.advanceToNextRow()  # raises StopIteration if depleted

                # Save keyframes every now and then
                if player.row - kf.row >= volatileKeyframeCounter:
                    volatileKeyframeCounter *= 2
                    self.saveKeyframe(player)

            assert player.row == goalRow
            player.callingNextWillAdvanceFrame = False  # let us re-obtain current frame by calling next()
        except StopIteration:
            # Depleted - make sure we get StopIteration next time we call `next`.
            assert player.callingNextWillAdvanceFrame
            assert player.lastArc.nextArc is None

        if oneOff:
            self.volatilePlayer = player

        return player

    def getCommitFrame(self, commit: Oid, unsafe=False) -> Frame:
        row = self.getCommitRow(commit)
        return self.getFrame(row, unsafe)

    def getFrame(self, row: int = 0, unsafe=False) -> Frame:
        assert row >= 0

        kfID = self.getBestKeyframeID(row)

        if kfID >= 0 and self.keyframes[kfID].row == row:
            # Cache hit
            frame = self.keyframes[kfID]
        else:
            # Cache miss
            frame = self.startPlayback(row)
            if not unsafe:
                frame = frame.sealCopy()

        assert frame.row == row, f"frame({int(frame.row)})/row({row}) mismatch"
        return frame

    def initialKeyframe(self):
        return Frame(
            row=BATCHROW_UNDEF,
            commit=self.startArc.openedBy,
            solvedArcs=[],
            openArcs=[],
            lastArc=self.startArc)

    def deleteKeyframesDependingOnRowsAbove(self, row: int):
        """
        Deletes all keyframes containing any arcs opened above the given row.
        """

        if len(self.keyframes) == 0:
            return

        # Get a starting keyframe for a row <= the desired row.
        kfID = self.getBestKeyframeID(row)
        if kfID < 0:
            kfID = 0

        # Fast-forward to the next keyframe with a row >= the desired row.
        while kfID < len(self.keyframes) and self.keyframes[kfID].row < row:
            kfID += 1

        # Once we reach keyframes occuring at a row >= `row`, see if we should stop deleting keyframes.
        # All open arcs, and all non-stale solved arcs, must be independent of rows <= `row`.
        while kfID < len(self.keyframes):
            kf = self.keyframes[kfID]

            if (all(arc is None or arc.isIndependentOfRowsAbove(row) for arc in kf.openArcs)
                    and all(arc is None or arc.isIndependentOfRowsAbove(row) or arc.isStale(row) for arc in kf.solvedArcs)):
                break
            else:
                kfID += 1

        # Delete the keyframes up to kfID.
        self.keyframes = self.keyframes[kfID:]
        self.keyframeRows = self.keyframeRows[kfID:]
        assert len(self.keyframes) == len(self.keyframeRows)

    def deleteArcsDependingOnRowsAbove(self, row: int):
        """
        Deletes all arcs opened before the given row.
        """

        if row == 0:
            return

        # In debug mode, bulldoze opening commits in dead arcs so they stand out in the debugger (make them dangling)
        if DEVDEBUG and self.startArc.nextArc:
            for deadArc in self.startArc.nextArc:
                if deadArc.openedAt >= row:
                    break
                deadArc.openedAt = BATCHROW_UNDEF
                deadArc.openedBy = DEAD_VALUE

        # Rewire top of list
        self.startArc.nextArc =\
            next((arc for arc in self.startArc if arc.openedAt >= row), None)

    def insertFront(self, frontGraph: Graph, numRowsToInsert: int):
        """
        Inserts contents of frontGraph at the beginning of this graph.
        (This function is invoked as step 2 of merging two graphs.)
        """

        # Graph to insert is empty? Bail.
        if frontGraph.startArc.nextArc is None:
            return

        # Don't want to insert any rows? Bail.
        if numRowsToInsert == 0:
            return

        # Find out the last arc we want to take from the front graph
        theirLastArc = next(arc for arc in frontGraph.startArc
                            if arc.nextArc is None or arc.nextArc.openedAt >= numRowsToInsert)
        assert theirLastArc is not None
        assert theirLastArc != frontGraph.startArc

        # In the arc linked list, rewire their last arc onto my first arc.
        theirLastArc.nextArc = self.startArc.nextArc

        # Rewire my top sentinel onto their first actual arc
        self.startArc.nextArc = frontGraph.startArc.nextArc

        # Steal their keyframes
        lastFrontKeyframeID = frontGraph.getBestKeyframeID(numRowsToInsert - 1)
        if lastFrontKeyframeID >= 0:
            assert len(self.keyframes) == len(self.keyframeRows)
            assert len(frontGraph.keyframes) == len(frontGraph.keyframeRows)
            self.keyframes = frontGraph.keyframes[:lastFrontKeyframeID + 1] + self.keyframes
            self.keyframeRows = frontGraph.keyframeRows[:lastFrontKeyframeID + 1] + self.keyframeRows

    def textDiagram(self, row0=0, maxRows=20):
        text = ""

        try:
            context = self.startPlayback(row0)
        except StopIteration:
            return F"Won't draw graph because it's empty below row {row0}!"

        for _ in context:
            frame = context.sealCopy()
            text += frame.textDiagram()
            maxRows -= 1
            if maxRows < 0:
                break

        return text

    def testConsistency(self):
        """ Very expensive consistency check for unit testing """

        # Verify chains
        if self.startArc.nextArc:
            for a in self.startArc.nextArc:
                logger.info(f"{a}")
                assert a.chain.isValid()

        # Verify keyframes
        playback = self.startPlayback(0)
        for row, keyframe in zip(self.keyframeRows, self.keyframes):
            playback.advanceToCommit(keyframe.commit)
            frame1 = playback.sealCopy()
            frame2 = keyframe.sealCopy()
            assert frame1 == frame2, f"Keyframe at row {row} doesn't match actual graph state"


class GraphSplicer:
    def __init__(self, oldGraph: Graph, oldHeads: Iterable[Oid], newHeads: Iterable[Oid]):
        self.keepGoing = True
        self.foundEquilibrium = False
        self.equilibriumNewRow = -1
        self.equilibriumOldRow = -1
        self.oldGraphRowOffset = 0

        self.newGraph = Graph()
        self.newGenerator = self.newGraph.startGenerator()

        self.oldGraph = oldGraph
        self.oldPlayer = oldGraph.startPlayback()

        # Commits that we must see before finding the equilibrium.
        newHeads = set(newHeads)
        oldHeads = set(oldHeads)
        self.requiredNewCommits = (newHeads - oldHeads)  # heads that appeared
        self.requiredOldCommits = (oldHeads - newHeads)  # heads that disappeared

        self.newCommitsSeen = set()
        self.oldCommitsSeen = set()

    def spliceNewCommit(self, newCommit: Oid, parentsOfNewCommit: list[Oid], keyframeInterval=KF_INTERVAL):
        assert self.keepGoing

        self.newCommitsSeen.add(newCommit)

        # Generate arcs for new frame.
        self.newGenerator.newCommit(newCommit, parentsOfNewCommit)

        # Save keyframe in new context every now and then.
        if int(self.newGenerator.row) % keyframeInterval == 0:
            self.newGraph.saveKeyframe(self.newGenerator)

        # Register this commit in the new graph's row sequence.
        self.newGraph.commitRows[newCommit] = self.newGenerator.row

        # Is it one of the commits that we must see before we can stop consuming new commits?
        if newCommit in self.requiredNewCommits:
            self.requiredNewCommits.remove(newCommit)

        # If the commit wasn't known in the old graph, don't advance the old graph.
        newCommitWasKnown = newCommit in self.oldGraph.commitRows
        if not newCommitWasKnown:
            return

        # The old graph's playback may be positioned past this commit already,
        # e.g. if branches were reordered. In that case, don't advance the old graph.
        if newCommit in self.oldPlayer.seenCommits:
            return

        # Alright, we know the commit is ahead in the old graph. Advance playback to it.
        try:
            oldCommitsPassed = self.oldPlayer.advanceToCommit(newCommit)
        except StopIteration:
            # Old graph depleted.
            self.keepGoing = False
            return

        # We just passed by some old commits; remove them from the set of old commits we need to see.
        if self.requiredOldCommits:
            self.requiredOldCommits.difference_update(oldCommitsPassed)

        # Keep track of any commits we may have skipped in the old graph,
        # because they are now unreachable and we want to purge them from the cache afterwards.
        self.oldCommitsSeen.update(oldCommitsPassed)

        # See if we're done: no more commits we want to see,
        # and the graph frames start being "equal" in both graphs.
        if len(self.requiredNewCommits) == 0 and \
                len(self.requiredOldCommits) == 0 and \
                self.isEquilibriumReached(self.newGenerator, self.oldPlayer):
            self.foundEquilibrium = True
            self.keepGoing = False
            return

    def finish(self):
        if self.foundEquilibrium:
            self.onEquilibriumFound()
        else:
            self.onOldGraphDepleted()
        self.keepGoing = False

    def onEquilibriumFound(self):
        """Completion with equilibrium"""

        # We'll basically concatenate newContext[eqNewRow:] and oldContext[:eqOldRow].
        equilibriumNewRow = int(self.newGenerator.row)
        equilibriumOldRow = int(self.oldPlayer.row)
        rowShiftInOldGraph = equilibriumNewRow - equilibriumOldRow

        logger.debug(f"Equilibrium: commit={str(self.oldPlayer.commit):.7} new={equilibriumNewRow} old={equilibriumOldRow}")

        # After reaching equilibrium there might still be open arcs that aren't closed yet.
        # Let's find out where they end before we can concatenate the graphs.
        equilibriumNewOpenArcs = list(filter(None, self.newGenerator.openArcs))
        equilibriumOldOpenArcs = list(filter(None, self.oldPlayer.sealCopy().openArcs))
        assert len(equilibriumOldOpenArcs) == len(equilibriumNewOpenArcs)

        # Fix up dangling open arcs in new graph
        for oldOpenArc, newOpenArc in zip(equilibriumOldOpenArcs, equilibriumNewOpenArcs):
            # Find out where the arc is resolved
            assert newOpenArc.openedBy == oldOpenArc.openedBy
            assert newOpenArc.closedBy == oldOpenArc.closedBy
            assert newOpenArc.closedAt == BATCHROW_UNDEF  # new graph's been interrupted before resolving this arc
            newOpenArc.closedAt = oldOpenArc.closedAt

            # Remap chain - the ChainHandle object is shared with all arcs on this chain
            newCH = newOpenArc.chain
            oldCH = oldOpenArc.chain
            assert newCH.topRow.isValid()
            assert oldCH.topRow.isValid()
            newCH.bottomRow = oldCH.bottomRow   # rewire bottom row BEFORE setting alias
            oldCH.setAliasOf(newCH)

            # Splice old junctions into new junctions
            if oldOpenArc.junctions:
                junctions = []
                junctions.extend(j for j in newOpenArc.junctions if j.joinedAt <= equilibriumNewRow)  # before eq
                junctions.extend(j for j in oldOpenArc.junctions if j.joinedAt > equilibriumOldRow)  # after eq
                assert all(junctions.count(x) == 1 for x in junctions), "duplicate junctions after splicing"
                newOpenArc.junctions = junctions

        # Do the actual splicing.

        # If we're adding a commit at the top of the graph, the closed arcs of the first keyframe will be incorrect,
        # so we must make sure to nuke the keyframe for equilibriumOldRow if it exists.
        with Benchmark("Delete lost keyframes"):
            self.oldGraph.deleteKeyframesDependingOnRowsAbove(equilibriumOldRow + 1)

        with Benchmark("Delete lost arcs"):
            self.oldGraph.deleteArcsDependingOnRowsAbove(equilibriumOldRow)

        with Benchmark("Delete lost rows"):
            for lostCommit in (self.oldCommitsSeen - self.newCommitsSeen):
                del self.oldGraph.commitRows[lostCommit]

        with Benchmark(F"Shift {len(self.oldGraph.ownBatches)} old batches by {rowShiftInOldGraph} rows"):
            BatchRow.BatchManager.shiftBatches(rowShiftInOldGraph, self.oldGraph.ownBatches)

        with Benchmark("Insert Front"):
            self.oldGraph.insertFront(self.newGraph, equilibriumNewRow)

        with Benchmark("Update row cache"):
            self.oldGraph.commitRows.update(self.newGraph.commitRows)
            self.oldGraph.ownBatches.extend(self.newGraph.ownBatches)  # Steal newGraph's batches
            self.newGraph.ownBatches = []  # Don't let newGraph nuke the batches in its __del__

        # Invalidate volatile player, which may be referring to dead keyframes
        self.oldGraph.volatilePlayer = None

        # Save rows for use by external code
        self.equilibriumNewRow = equilibriumNewRow
        self.equilibriumOldRow = equilibriumOldRow
        self.oldGraphRowOffset = rowShiftInOldGraph

    def onOldGraphDepleted(self):
        """Completion without equilibrium: no more commits in oldGraph"""

        # If we exited the loop without reaching equilibrium, the whole graph has changed.
        # In that case, steal the contents of newGraph, and bail.

        self.equilibriumOldRow = self.oldPlayer.row
        self.equilibriumNewRow = self.newGenerator.row
        self.oldGraphRowOffset = 0

        self.oldGraph.shallowCopyFrom(self.newGraph)

    @staticmethod
    def isEquilibriumReached(frameA: Frame, frameB: Frame):
        rowA = frameA.row
        rowB = frameB.row

        for arcA, arcB in itertools.zip_longest(frameA.openArcs, frameB.openArcs):
            isStaleA = (not arcA) or arcA.isStale(rowA)
            isStaleB = (not arcB) or arcB.isStale(rowB)

            if isStaleA != isStaleB:
                return False

            if isStaleA:
                assert isStaleB
                continue

            assert arcA.lane == arcB.lane

            if not (arcA.openedBy == arcB.openedBy and arcA.closedBy == arcB.closedBy):
                return False

        # Do NOT test solved arcs!
        return True
