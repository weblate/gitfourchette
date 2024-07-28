import dataclasses
import logging

from gitfourchette.graph.graph import Graph, BatchRow, KF_INTERVAL, Oid
from gitfourchette.graph.graphtrickle import GraphTrickle
from gitfourchette.graph.graphsplicer import GraphSplicer
from gitfourchette.graph.graphweaver import GraphWeaver
from gitfourchette.toolbox import Benchmark

logger = logging.getLogger(__name__)


def _ensureSet(x):
    if x is None:
        return set()
    assert type(x) is not dict
    if type(x) is not set:
        return set(x)
    assert type(x) is set
    return x


@dataclasses.dataclass
class MockCommit:
    id: Oid
    parent_ids: list[Oid]


class GraphBuildLoop:
    def __init__(
            self,
            heads=None,
            hideSeeds=None,
            localSeeds=None,
            forceHide=None,
            keyframeInterval=KF_INTERVAL
    ):
        heads = _ensureSet(heads)
        hideSeeds = _ensureSet(hideSeeds)
        if localSeeds is None:
            localSeeds = heads   # all heads local by default
        localSeeds = _ensureSet(localSeeds)

        self.graph, self.weaver = GraphWeaver.newGraph()
        self.hiddenTrickle = GraphTrickle.newHiddenTrickle(heads, hideSeeds, forceHide)
        self.foreignTrickle = GraphTrickle.newForeignTrickle(heads, localSeeds)
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
            oldHeads: set[Oid],
            newHeads: set[Oid],
            hideSeeds: set[Oid] = None,
            localSeeds: set[Oid] = None,
            keyframeInterval=KF_INTERVAL,
    ):
        if localSeeds is None:
            localSeeds = newHeads   # all heads local by default

        oldHeads = _ensureSet(oldHeads)
        newHeads = _ensureSet(newHeads)
        hideSeeds = _ensureSet(hideSeeds)
        localSeeds = _ensureSet(localSeeds)

        self.graph = graph
        self.oldCommitSequence = oldCommitSequence
        self.commitSequence = None  # unknown yet
        self.oldHeads = oldHeads
        self.newHeads = newHeads
        self.hideSeeds = hideSeeds
        self.localSeeds = localSeeds
        self.keyframeInterval = keyframeInterval

        self.splicer = GraphSplicer(self.graph, self.oldHeads, self.newHeads)
        self.hiddenTrickle = GraphTrickle.newHiddenTrickle(self.newHeads, self.hideSeeds)
        self.foreignTrickle = GraphTrickle.newForeignTrickle(self.newHeads, self.localSeeds)

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
        # Keep feeding commits to trickle until it stabilizes.
        if splicer.foundEquilibrium:
            with Benchmark("Stabilize trickles"):
                row = nAdded + 1
                r1 = self._stabilizeTrickle(hiddenTrickle, row, newCommitSequence)
                r2 = self._stabilizeTrickle(foreignTrickle, row, newCommitSequence)
            logger.debug(f"Trickle stabilization: Hidden={r1}; Foreign={r2}")

        self.numRowsRemoved = nRemoved
        self.numRowsAdded = nAdded
        self.commitSequence = newCommitSequence

    @staticmethod
    def _stabilizeTrickle(trickle: GraphTrickle, startRow: int, newCommitSequence: list[MockCommit]):
        for row in range(startRow, len(newCommitSequence)):
            commit = newCommitSequence[row]
            trickle.newCommit(commit.id, commit.parent_ids)

            # See if finished (not too often - expensive)
            if ((row & 0xFF) == 0) and trickle.done:
                return row

    @property
    def hiddenCommits(self):
        return self.hiddenTrickle.flaggedSet

    @property
    def foreignCommits(self):
        return self.foreignTrickle.flaggedSet
