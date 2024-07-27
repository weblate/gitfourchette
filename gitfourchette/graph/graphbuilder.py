import dataclasses
import logging

from gitfourchette.graph.graph import Graph, BatchRow, KF_INTERVAL, Oid
from gitfourchette.graph.graphtrickle import GraphTrickle
from gitfourchette.graph.graphsplicer import GraphSplicer
from gitfourchette.graph.graphweaver import GraphWeaver
from gitfourchette.toolbox import Benchmark

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class MockCommit:
    id: Oid
    parent_ids: list[Oid]


class GraphBuildLoop:
    def __init__(
            self,
            heads=None,
            hiddenTips=None,
            hiddenTaps=None,
            localHeads=None,
            keyframeInterval=KF_INTERVAL
    ):
        heads = heads or []
        hiddenTips = hiddenTips or []
        if localHeads is None:
            localHeads = heads   # all heads local by default

        self.graph, self.weaver = GraphWeaver.newGraph()
        self.hiddenTrickle = GraphTrickle.initForHiddenCommits(heads, hiddenTips, hiddenTaps)
        self.foreignTrickle = GraphTrickle.initForForeignCommits(heads, localHeads)
        self.keyframeInterval = keyframeInterval

    def sendAll(self, sequence):
        gen = self.coBuild()
        gen.send(None)  # prime it
        for c in sequence:
            gen.send(c)
        gen.close()
        return self

    def onKeyframe(self, i):
        pass

    def coBuild(self):
        graph = self.graph
        weaver = self.weaver
        hiddenTrickle = self.hiddenTrickle
        foreignTrickle = self.foreignTrickle
        keyframeInterval = self.keyframeInterval

        while True:
            try:
                commit = yield
            except GeneratorExit:
                break

            oid = commit.id
            parents = commit.parent_ids

            weaver.newCommit(oid, parents)
            hiddenTrickle.newCommit(oid, parents)
            foreignTrickle.newCommit(oid, parents)

            row = weaver.row
            rowInt = int(row)
            assert type(row) is BatchRow
            assert rowInt >= 0
            graph.commitRows[oid] = row

            # Save keyframes at regular intervals for faster random access.
            if rowInt % keyframeInterval == 0:
                graph.saveKeyframe(weaver)
                self.onKeyframe(rowInt)

        logger.debug(f"Peak arc count: {weaver.peakArcCount}")

    @property
    def hiddenCommits(self):
        return self.hiddenTrickle.flaggedSet

    @property
    def foreignCommits(self):
        return self.foreignTrickle.flaggedSet


class GraphSpliceLoop:
    def __init__(
            self,
            graph: Graph,
            oldCommitSequence: list[MockCommit],
            oldHeads,
            newHeads,
            hiddenTips: set[Oid] = None,
            localHeads: set[Oid] = None,
            hiddenCommits: set[Oid] = None,
            foreignCommits: set[Oid] = None,
            keyframeInterval=KF_INTERVAL,
    ):
        oldHeads = oldHeads or []
        newHeads = newHeads or []
        hiddenTips = hiddenTips or []
        if localHeads is None:
            localHeads = newHeads   # all heads local by default
        if hiddenCommits is None:
            hiddenCommits = set()
        if foreignCommits is None:
            foreignCommits = set()

        self.graph = graph
        self.oldCommitSequence = oldCommitSequence
        self.commitSequence = None  # unknown yet
        self.oldHeads = oldHeads
        self.newHeads = newHeads
        self.hiddenTips = hiddenTips
        self.localTips = localHeads
        self.keyframeInterval = keyframeInterval

        self.splicer = GraphSplicer(self.graph, self.oldHeads, self.newHeads)
        self.hiddenTrickle = GraphTrickle.initForHiddenCommits(self.newHeads, self.hiddenTips, patchFlaggedSet=hiddenCommits)
        self.foreignTrickle = GraphTrickle.initForForeignCommits(self.newHeads, self.localTips, patchFlaggedSet=foreignCommits)

        self.numRowsRemoved = 0
        self.numRowsAdded = 0

    def sendAll(self, sequence):
        gen = self.coSplice()
        gen.send(None)  # prime it
        for c in sequence:
            try:
                gen.send(c)
            except StopIteration:
                break
        gen.close()
        return self

    def coSplice(self):
        newCommitSequence = []
        splicer = self.splicer
        hiddenTrickle = self.hiddenTrickle
        foreignTrickle = self.foreignTrickle

        while splicer.keepGoing:
            try:
                commit = yield
            except GeneratorExit:
                break
            oid = commit.id
            parents = commit.parent_ids

            newCommitSequence.append(commit)
            splicer.spliceNewCommit(oid, parents, self.keyframeInterval)
            hiddenTrickle.newCommit(oid, parents)
            foreignTrickle.newCommit(oid, parents)

        splicer.finish()

        if splicer.foundEquilibrium:
            nRemoved = splicer.equilibriumOldRow
            nAdded = splicer.equilibriumNewRow
        else:
            nRemoved = -1  # We could use len(self.commitSequence), but -1 will force refreshRepo to replace the model wholesale
            nAdded = len(newCommitSequence)

        # Piece correct commit sequence back together
        with Benchmark("Reassemble commit sequence"):
            if not splicer.foundEquilibrium:
                pass  # keep newCommitSequence
            elif nAdded == 0 and nRemoved == 0:
                newCommitSequence = self.oldCommitSequence
            elif nRemoved == 0:
                newCommitSequence = newCommitSequence[:nAdded] + self.oldCommitSequence
            else:
                newCommitSequence = newCommitSequence[:nAdded] + self.oldCommitSequence[nRemoved:]

        # Finish patching hidden/foreign commit sets.
        # Keep feeding commits to trickle until it stabilizes to its previous state.
        if splicer.foundEquilibrium:
            with Benchmark("Finish patching hidden/foreign commits"):
                row = nAdded + 1
                r1 = self._stabilizeTrickle(hiddenTrickle, row, newCommitSequence)
                r2 = self._stabilizeTrickle(foreignTrickle, row, newCommitSequence)
                logger.debug(f"Trickle stabilization: Hidden={r1}; Foreign={r2}")

        self.numRowsRemoved = nRemoved
        self.numRowsAdded = nAdded
        self.commitSequence = newCommitSequence

    @staticmethod
    def _stabilizeTrickle(trickle: GraphTrickle, startRow: int, newCommitSequence: list[MockCommit]):
        if trickle.done:
            return startRow

        for row in range(startRow, len(newCommitSequence)):
            commit = newCommitSequence[row]

            wasFlagged = commit.id in trickle.flaggedSet
            isFlagged = trickle.newCommit(commit.id, commit.parent_ids)

            stabilized = (wasFlagged == isFlagged) or trickle.done
            if stabilized:
                return row
