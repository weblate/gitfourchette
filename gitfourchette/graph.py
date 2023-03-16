from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass
from gitfourchette import log
from gitfourchette.benchmark import Benchmark
from pygit2 import Oid
from typing import Iterable
import bisect
import itertools


KF_INTERVAL = 5000
ABRIDGMENT_THRESHOLD = 25
DEAD_VALUE = "!DEAD"


@dataclass
class ArcJunction:
    """ Represents the merging of an Arc into another Arc. """

    joinedAt: int  # Row number in which this junction occurs
    joinedBy: Oid  # Hash of the joining arc's opening commit

    def __lt__(self, other):
        """
        Calling sorted() on a list of ArcJunctions will sort them by `joinedAt` (row numbers).
        """
        return self.joinedAt < other.joinedAt

    def copyWithOffset(self, offset):
        return ArcJunction(self.joinedAt + offset, self.joinedBy)


@dataclass
class Arc:
    """ An arc connects two commits in the graph.

    Commits appear before their parents in the commit sequence.
    When processing the commit sequence, we "open" a new arc when
    encountering a new commit. The arc stays "open" until we've found
    the commit's parent in the sequence, at which point we "close" it.

    Other arcs may merge into an open arc via an ArcJunction.
    """

    openedAt: int  # Row number in which this arc was opened
    closedAt: int  # Row number in which this arc was closed
    lane: int  # Lane assigned to this arc
    openedBy: Oid  # Hash of the opening commit (in git parlance, the child commit)
    closedBy: Oid  # Hash of the closing commit (in git parlance, the parent commit)
    junctions: list[ArcJunction]  # Other arcs merging into this arc
    nextArc: Arc | None = None  # Next node in the arc linked list

    def __repr__(self):
        s = F"{str(self.openedBy)[:5]}->{str(self.closedBy)[:5]}"
        if self.closedAt < 0:
            s += "?"
        else:
            s += "."
        return s

    def length(self):
        return self.closedAt - self.openedAt

    def __next__(self):
        return self.nextArc

    def __iter__(self):
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

    def isParentlessCommit(self):
        return self.openedBy == self.closedBy

    def connectsHiddenCommit(self, hiddenCommits: set):
        return self.openedBy in hiddenCommits or self.closedBy in hiddenCommits

    def isIndependentOfRowsAbove(self, row: int):
        """ Return True if this arc is entirely independent of row numbers lower than `row`. """
        return self.openedAt >= row and self.closedAt >= row

    def isStale(self, row: int):
        return 0 <= self.closedAt < row


@dataclass
class Frame:
    """ A frame is a slice of the graph at a given row. """

    row: int
    commit: Oid
    solvedArcs: list[Arc | None]  # Arcs that have resolved their parent commit
    openArcs: list[Arc | None]  # Arcs that have not resolved their parent commit yet
    lastArc: Arc

    def getArcsClosedByCommit(self):
        return filter(lambda arc: arc and arc.closedAt == self.row, self.solvedArcs)

    def getArcsOpenedByCommit(self):
        return filter(lambda arc: arc and arc.openedAt == self.row, self.openArcs)

    def getArcsPassingByCommit(self):
        return filter(lambda arc: arc and arc.openedAt != self.row, self.openArcs)

    def getHomeLaneForCommit(self):
        leftmostClosed = next(self.getArcsClosedByCommit(), None)
        leftmostOpened = next(self.getArcsOpenedByCommit(), None)
        if leftmostOpened and leftmostClosed:
            return max(leftmostClosed.lane, leftmostOpened.lane)
        elif leftmostClosed:
            return leftmostClosed.lane
        elif leftmostOpened:
            return leftmostOpened.lane
        else:
            # It's a parentless + childless commit.
            # Implementation detail: for parentless commits, we create a bogus arc
            # as the "last" arc in the frame; we can get the lane from this bogus arc.
            assert self.lastArc.isParentlessCommit()
            assert self.lastArc.openedBy == self.commit
            return self.lastArc.lane

    def copyCleanFrame(self) -> Frame:
        solvedArcsCopy = self.solvedArcs.copy()
        openArcsCopy = self.openArcs.copy()

        # Clean up arcs that just got closed
        for lane, arc in enumerate(openArcsCopy):
            if arc and 0 <= arc.closedAt <= self.row:
                self.reserveArcListCapacity(solvedArcsCopy, lane+1)
                solvedArcsCopy[lane] = arc
                openArcsCopy[lane] = None

        # Remove stale closed arcs and trim "Nones" off end of list
        self.cleanUpArcList(openArcsCopy, self.row, alsoTrimBack=True)
        self.cleanUpArcList(solvedArcsCopy, self.row, alsoTrimBack=True)

        # In debug mode, make sure none of the arcs are dangling
        assert all(arc is None or arc.openedBy != DEAD_VALUE for arc in openArcsCopy)
        assert all(arc is None or arc.openedBy != DEAD_VALUE for arc in solvedArcsCopy)

        return Frame(self.row, self.commit, solvedArcsCopy, openArcsCopy, self.lastArc)

    def isEquilibriumReached(self, peer):
        for mine, theirs in itertools.zip_longest(self.openArcs, peer.openArcs):
            mineIsStale = (not mine) or (0 <= mine.closedAt < self.row)
            theirsIsStale = (not theirs) or (0 <= theirs.closedAt < peer.row)

            if mineIsStale != theirsIsStale:
                return False

            if mineIsStale:
                assert theirsIsStale
                continue

            assert mine.lane == theirs.lane

            if not (mine.openedBy == theirs.openedBy and mine.closedBy == theirs.closedBy):
                return False

        # Do NOT test non-open arcs!
        return True

    @staticmethod
    def reserveArcListCapacity(theList, newLength):
        if len(theList) >= newLength:
            return
        for i in range(newLength - len(theList)):
            theList.append(None)

    @staticmethod
    def cleanUpArcList(theList: list[Arc|None], olderThanRow: int, alsoTrimBack: bool = True):
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

        columnAbove, columnBelow = -1, -1
        laneRemap = []

        solvedArc: Arc
        openArc: Arc
        for solvedArc, openArc in itertools.zip_longest(self.solvedArcs, self.openArcs):
            if openArc and not openArc.connectsHiddenCommit(hiddenCommits):
                columnBelow += 1
                if openArc.openedAt < self.row:
                    columnAbove += 1
            if solvedArc and not solvedArc.connectsHiddenCommit(hiddenCommits):
                columnAbove += 1
            laneRemap.append( (columnAbove, columnBelow) )

        numFlattenedLanes = max(columnAbove, columnBelow)

        return laneRemap, numFlattenedLanes


class GeneratorState(Frame):
    freeLanes: list[int]
    parentLookup: defaultdict[Oid, list[Arc]]  # all lanes

    def __init__(self, startArcSentinel: Arc):
        super().__init__(-1, "", [], [], lastArc=startArcSentinel)
        self.freeLanes = []
        self.parentLookup = defaultdict(list)

    def createArcsForNewCommit(self, me: Oid, myParents: list[Oid], allocLanesInGaps: bool):
        self.row += 1
        self.commit = me

        hasParents = len(myParents) > 0

        # Close arcs that my child commits opened higher up in the graph, waiting for me to appear in the commit sequence
        myOpenArcs = self.parentLookup.get(me)
        myHomeLane = -1
        handOffHomeLane = False
        if myOpenArcs is not None:
            myHomeLane = sorted(myOpenArcs, key=lambda arc: arc.lane)[0].lane
            for arc in myOpenArcs:
                assert arc.closedBy == me
                assert arc.closedAt == -1
                arc.closedAt = self.row
                self.solvedArcs[arc.lane] = arc
                self.openArcs[arc.lane] = None  # Free up the lane below
                if hasParents and arc.lane == myHomeLane:
                    handOffHomeLane = True
                elif allocLanesInGaps:
                    bisect.insort(self.freeLanes, arc.lane)
            del self.parentLookup[me]

            # Compact null arcs at right of graph
            if not allocLanesInGaps:
                for _ in range(len(self.openArcs)-1, myHomeLane, -1):
                    if self.openArcs[-1] is not None:
                        break
                    self.openArcs.pop()
                    self.solvedArcs.pop()

        firstParentFound = False
        for parent in myParents:
            # See if there's already an arc for my parent
            if firstParentFound:
                arcsOfParent = self.parentLookup.get(parent)
                if arcsOfParent:
                    arcsOfParent = sorted(arcsOfParent, key=lambda arc: arc.lane)
                    arc = arcsOfParent[0]
                    assert arc.closedBy == parent
                    assert arc.closedAt == -1
                    arc.junctions.append(ArcJunction(joinedAt=self.row, joinedBy=me))
                    continue

            # Get a free lane
            if not firstParentFound and myHomeLane >= 0:
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

            newArc = Arc(self.row, -1, freeLane, me, parent, [], None)
            self.openArcs[freeLane] = newArc
            self.parentLookup[parent].append(newArc)
            self.lastArc.nextArc = newArc
            self.lastArc = newArc

            firstParentFound = True

        # Parentless commit: we'll insert a bogus arc so playback doesn't need the commit sequence.
        # This is just to keep the big linked list of arcs flowing.
        # Do NOT put it in solved or open arcs! This would interfere with detection of arcs that the commit
        # actually closes or opens.
        if not firstParentFound:
            if myHomeLane < 0:
                # Edge case: the commit is BOTH childless AND parentless.
                # Put the commit in a free lane, but do NOT reserve the lane.
                if not self.freeLanes:
                    myHomeLane = len(self.openArcs)
                else:
                    myHomeLane = self.freeLanes[0]  # PEEK only! do not pop!
            newArc = Arc(self.row, self.row, myHomeLane, me, me, [], None)
            self.lastArc.nextArc = newArc
            self.lastArc = newArc

        assert not handOffHomeLane
        assert len(self.openArcs) == len(self.solvedArcs)


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
        goalRow = -1
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
    keyframeRows: list[int] | None
    startArc: Arc  # linked list start sentinel; guaranteed to never be None

    def __init__(self):
        self.clear()

    def clear(self):
        self.keyframes = []
        self.keyframeRows = []
        self.startArc = Arc(-1, -1, -1, "!TOP", "!BOTTOM", [], None)

    def shallowCopyFrom(self, source):
        self.keyframes = source.keyframes
        self.keyframeRows = source.keyframeRows
        self.startArc = source.startArc

    def isEmpty(self):
        return self.startArc.nextArc is None

    def generateFullSequence(self, sequence: list[Oid], parentsOf: dict[Oid, list[Oid]], allocLanesInGaps: bool):
        cacher = GeneratorState(self.startArc)

        for me in sequence:
            cacher.createArcsForNewCommit(me, parentsOf[me], allocLanesInGaps)
            if cacher.row % KF_INTERVAL == 0:
                self.saveKeyframe(cacher)

    def saveKeyframe(self, frame: Frame) -> int:
        assert len(self.keyframes) == len(self.keyframeRows)

        kf = frame.copyCleanFrame()

        kfID = bisect.bisect_left(self.keyframeRows, frame.row)
        if kfID < len(self.keyframes) and self.keyframes[kfID].row == frame.row:
            assert self.keyframes[kfID] == kf
            log.info("Graph", "Not overwriting existing keyframe", kfID)
            return kfID

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
        assert len(self.keyframes) == len(self.keyframeRows)

        bestKeyframeID = bisect.bisect_right(self.keyframeRows, row) - 1
        if bestKeyframeID < 0:
            return -1

        bestKeyframeRow = self.keyframeRows[bestKeyframeID]
        assert 0 <= bestKeyframeRow <= row

        return bestKeyframeID

    def startGenerator(self) -> GeneratorState:
        assert self.isEmpty(), "cannot re-cache an existing graph!"
        return GeneratorState(self.startArc)

    def startPlayback(self, goalRow: int = 0) -> PlaybackState:
        kfID = self.getBestKeyframeID(goalRow)
        if kfID >= 0:
            kf = self.keyframes[kfID]
        else:
            kf = self.getKF0()

        player = PlaybackState(kf)

        # Position playback context on target row
        try:
            volatileKeyframeCounter = 1
            assert player.row <= goalRow
            while player.row < goalRow:
                player.advanceToNextRow()  # raises StopIteration if depleted
                if player.row - kf.row >= volatileKeyframeCounter:
                    volatileKeyframeCounter *= 2
                    self.saveKeyframe(player)
            assert player.row == goalRow
            player.callingNextWillAdvanceFrame = False  # let us re-obtain current frame by calling next()
        except StopIteration:
            # Depleted - make sure we get StopIteration next time we call `next`.
            assert player.callingNextWillAdvanceFrame
            assert player.lastArc.nextArc is None

        return player

    def getFrame(self, row: int = 0) -> Frame:
        kfID = self.getBestKeyframeID(row)

        if kfID >= 0 and self.keyframes[kfID].row == row:
            # Cache hit
            frame = self.keyframes[kfID]
        else:
            # Cache miss
            frame = self.startPlayback(row).copyCleanFrame()

        assert frame.row == row
        return frame

    def startSplicing(self, oldHeads: set[Oid], newHeads: set[Oid]) -> GraphSplicer:
        return GraphSplicer(self, oldHeads, newHeads)

    def getKF0(self):
        return Frame(
            row=-1,
            commit=self.startArc.openedBy,
            solvedArcs=[],
            openArcs=[],
            lastArc=self.startArc)

    def deleteKeyframesWithArcsOpenedAbove(self, row: int):
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

        # Invalidate keyframe row cache.
        self.keyframeRows = None

    def deleteArcsOpenedAbove(self, row):
        """
        Deletes all arcs opened before the given row.
        """

        if row == 0:
            return

        # In debug mode, bulldoze opening commits in dead arcs so they stand out in the debugger (make them dangling)
        if __debug__:
            for deadArc in self.startArc:
                if deadArc.openedAt >= row:
                    break
                if deadArc != self.startArc:
                    deadArc.openedBy = DEAD_VALUE

        # Rewire top of list
        self.startArc.nextArc =\
            next((arc for arc in self.startArc if arc.openedAt >= row), None)

    def shiftRows(self, rowOffset: int):
        """
        Apply an offset to all rows referenced by arcs and keyframes.
        """

        if rowOffset == 0:
            return

        # Shift rows in remaining keyframes
        for kf in self.keyframes:
            kf.row += rowOffset

        # Shift rows in remaining arcs
        for arc in self.startArc:
            if arc.openedAt >= 0:
                arc.openedAt += rowOffset
            if arc.closedAt >= 0:
                arc.closedAt += rowOffset
            if arc.junctions:
                for junction in arc.junctions:
                    junction.joinedAt += rowOffset

    def insertFront(self, frontGraph, numRowsToInsert):
        """
        Inserts contents of frontGraph at the beginning of this graph.
        Does not offset row indices!
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
            self.keyframes = frontGraph.keyframes[:lastFrontKeyframeID + 1] + self.keyframes
            self.keyframeRows = None  # Invalidate cache of keyframe rows

    def recreateKeyframeRowCache(self):
        """
        Recreates the cache of keyframe rows (for bisecting).
        """

        self.keyframeRows = [kf.row for kf in self.keyframes]


class GraphSplicer:
    def __init__(self, oldGraph: Graph, oldHeads: Iterable[Oid], newHeads: Iterable[Oid]):
        self.keepGoing = True
        self.foundEquilibrium = False

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

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Convenience context manager so you don't have to call finish() manually.
        """
        self.finish()

    def spliceNewCommit(self, newCommit: Oid, parentsOfNewCommit: list[Oid], newCommitWasKnown: bool, allocLanesInGaps: bool):
        self.newCommitsSeen.add(newCommit)

        # Generate arcs for new frame.
        self.newGenerator.createArcsForNewCommit(newCommit, parentsOfNewCommit, allocLanesInGaps)

        # Save keyframe in new context.
        if self.newGenerator.row % KF_INTERVAL == 0:
            self.newGraph.saveKeyframe(self.newGenerator)

        # Is it one of the commits that we must see before we can stop consuming new commits?
        if newCommit in self.requiredNewCommits:
            self.requiredNewCommits.remove(newCommit)

        # If the commit wasn't known in the old graph, don't advance the old graph.
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
        equilibriumNewRow = self.newGenerator.row
        equilibriumOldRow = self.oldPlayer.row
        rowShiftInOldGraph = equilibriumNewRow - equilibriumOldRow

        log.info("GraphSplicer", F"FOUND EQUILIBRIUM @new={equilibriumNewRow};old={equilibriumOldRow}!")

        # After reaching equilibrium there might still be open arcs that aren't closed yet.
        # Let's find out where they end before we can concatenate the graphs.
        equilibriumNewOpenArcs = list(filter(None, self.newGenerator.openArcs))
        equilibriumOldOpenArcs = list(filter(None, self.oldPlayer.copyCleanFrame().openArcs))
        assert len(equilibriumOldOpenArcs) == len(equilibriumNewOpenArcs)

        for oldOpenArc, newOpenArc in zip(equilibriumOldOpenArcs, equilibriumNewOpenArcs):
            assert newOpenArc.openedBy == oldOpenArc.openedBy
            # Find out where open arc ends.
            newOpenArc.closedAt = oldOpenArc.closedAt + rowShiftInOldGraph
            # Splice old junctions into new junctions.
            if oldOpenArc.junctions:
                newOpenArc.junctions = self.spliceJunctions(equilibriumOldRow, equilibriumNewRow, oldOpenArc.junctions, newOpenArc.junctions)

        # Do the actual splicing.

        # If we're adding a commit at the top of the graph, the closed arcs of the first keyframe will be incorrect,
        # so we must make sure to nuke the keyframe for equilibriumOldRow if it exists.
        with Benchmark(F"Delete Keyframes"):
            self.oldGraph.deleteKeyframesWithArcsOpenedAbove(equilibriumOldRow + 1)
        with Benchmark(F"Delete Arcs"):
            self.oldGraph.deleteArcsOpenedAbove(equilibriumOldRow)
        with Benchmark(F"Shift Rows by {rowShiftInOldGraph}"):
            self.oldGraph.shiftRows(rowShiftInOldGraph)
        with Benchmark("Insert Front"):
            self.oldGraph.insertFront(self.newGraph, equilibriumNewRow)
        with Benchmark("Recreate Keyframe Row Cache"):
            self.oldGraph.recreateKeyframeRowCache()

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
        for arcA, arcB in itertools.zip_longest(frameA.openArcs, frameB.openArcs):
            isStaleA = (not arcA) or (0 <= arcA.closedAt < frameA.row)
            isStaleB = (not arcB) or (0 <= arcB.closedAt < frameB.row)

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

    @staticmethod
    def spliceJunctions(oldEqRow, newEqRow, oldJunctions, newJunctions):
        oldOffset = newEqRow - oldEqRow

        spliced = []

        # Copy junctions before equilibrium
        spliced.extend( j for j in newJunctions if j.joinedAt <= newEqRow )

        # Copy junctions after equilibrium (with offset)
        spliced.extend( j.copyWithOffset(oldOffset) for j in oldJunctions if j.joinedAt > oldEqRow )

        # Ensure the resulting list is sorted and contains no duplicates
        assert spliced == sorted(spliced), "spliced list of junctions isn't sorted!"
        assert all(spliced.count(x) == 1 for x in spliced),\
            "spliced list of junctions contains duplicates!"  # can't do set(spliced) because Junction isn't frozen

        return spliced

