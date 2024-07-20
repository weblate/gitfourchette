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

    @staticmethod
    def initForHiddenCommits(allHeads, hiddenTips, hiddenTaps=None):
        trickle = GraphTrickle()

        # Explicitly show all refs by default
        for head in allHeads:
            trickle.setEnd(head)

        # Explicitly hide tips
        for hiddenBranchTip in hiddenTips:
            trickle.setPipe(hiddenBranchTip)

        # # Explicitly hide stash junk parents
        # if settings.prefs.hideStashJunkParents:
        #     for stash in self.repo.listall_stashes():
        #         stashCommit = self.repo.peel_commit(stash.commit_id)
        #         for i, parent in enumerate(stashCommit.parent_ids):
        #             if i > 0:
        #                 trickle.setTap(parent)
        if hiddenTaps:
            for hiddenTap in hiddenTaps:
                trickle.setTap(hiddenTap)

        return trickle

    @staticmethod
    def initForForeignCommits(refsAt):
        trickle = GraphTrickle()

        for oid, refList in refsAt.items():
            assert oid not in trickle.frontier
            isLocal = any(name == "HEAD" or name.startswith("refs/heads/") for name in refList)
            if isLocal:
                trickle.setEnd(oid)
            else:
                trickle.setPipe(oid)

        return trickle
