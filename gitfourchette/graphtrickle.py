from gitfourchette.porcelain import Oid

END = 0
PIPE = 1
TAP = 2


class GraphTrickle:
    def __init__(self):
        self.frontier = {}

    def setEnd(self, commit: Oid):
        self.frontier[commit] = END

    def setPipe(self, commit: Oid):
        self.frontier[commit] = PIPE

    def setTap(self, commit: Oid):
        self.frontier[commit] = TAP

    @property
    def done(self) -> bool:
        frontier = self.frontier
        return all(not frontier[k] for k in self.frontier.keys())

    def newCommit(
            self,
            commit: Oid,
            parents: list[Oid],
            flaggedSet: set[Oid],
            discard: bool = False
    ) -> bool:
        frontier = self.frontier
        flagged = frontier.pop(commit, END)

        if flagged:
            # Trickle through parents that are not explicitly flagged
            for p in parents:
                frontier.setdefault(p, PIPE)

            flaggedSet.add(commit)

        else:
            # Block trickling to parents (that aren't taps themselves)
            for p in parents:
                if frontier.get(p, END) < TAP:
                    frontier[p] = END

            if discard:
                flaggedSet.discard(commit)

        return bool(flagged)
