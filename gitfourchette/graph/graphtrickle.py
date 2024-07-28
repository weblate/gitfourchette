from gitfourchette.porcelain import Oid

STOP = 0
PIPE = 1
SOURCE = 2


class GraphTrickle:
    def __init__(self):
        self.frontier = {}
        self.flaggedSet = set()

    @property
    def done(self) -> bool:
        return all(v == STOP for v in self.frontier.values())

    def newCommit(self, commit: Oid, parents: list[Oid]):
        frontier = self.frontier
        flagged = frontier.pop(commit, STOP)

        if flagged != STOP:
            # Trickle through parents that are not explicitly flagged
            for p in parents:
                frontier.setdefault(p, PIPE)
            self.flaggedSet.add(commit)
        else:
            # Block trickling to parents (that aren't sources themselves)
            for p in parents:
                if frontier.get(p, STOP) != SOURCE:
                    frontier[p] = STOP

    @staticmethod
    def newHiddenTrickle(
            allHeads: set[Oid],
            hideSeeds: set[Oid],
            forceHide: set[Oid] | None = None
    ):
        trickle = GraphTrickle()

        # Explicitly show all refs by default (block foreign trickle)
        for head in allHeads:
            trickle.frontier[head] = STOP

        # Explicitly hide tips (allow foreign trickle)
        for head in hideSeeds:
            trickle.frontier[head] = PIPE

        # Explicitly hide stash junk parents (beyond parent #0)
        # NOTE: Dropped this from the actual app but kept around in unit tests.
        if forceHide:
            for head in forceHide:
                trickle.frontier[head] = SOURCE

        return trickle

    @staticmethod
    def newForeignTrickle(
            allHeads: set[Oid],
            localSeeds: set[Oid]
    ):
        trickle = GraphTrickle()

        # Start with all foreign heads
        for head in allHeads:
            trickle.frontier[head] = PIPE

        # Local heads block propagation of foreign trickle
        for head in localSeeds:
            trickle.frontier[head] = STOP

        return trickle
