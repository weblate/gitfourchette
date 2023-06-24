import enum
import pygit2

Oid = pygit2.Oid


class HiddenCommitSolver:
    @enum.unique
    class Tag(enum.IntEnum):
        NONE = 0
        SOFTHIDE = 1
        HARDHIDE = 2
        SHOW = 3

    def __init__(self):
        self.tags = {}

    def tagCommit(self, commit: pygit2.Oid, tag: Tag):
        self.tags[commit] = tag

    @property
    def done(self) -> bool:
        return len(self.tags) == 0

    def newCommit(self, commit: Oid, parents: list[Oid], marked: set[Oid], discard: bool = False):
        T = HiddenCommitSolver.Tag
        tag = self.tags.pop(commit, T.NONE)

        if tag in [T.SOFTHIDE, T.HARDHIDE]:
            for p in parents:
                if p not in self.tags:
                    self.tags[p] = T.SOFTHIDE
            marked.add(commit)
        else:
            for p in parents:
                ctag = self.tags.get(p, T.NONE)
                if ctag != T.HARDHIDE:
                    self.tags[p] = T.SHOW
            if discard:
                marked.discard(commit)


class ForeignCommitSolver:
    def __init__(self, commitsToRefs: dict[Oid, list[str]]):
        self._nextLocal = set()
        for commitOid, refList in commitsToRefs.items():
            if any(name == 'HEAD' or name.startswith("refs/heads/") for name in refList):
                self._nextLocal.add(commitOid)

    def setLocal(self, commit: Oid):
        self._nextLocal.add(commit)

    def newCommit(self, commit: Oid, parents: list[Oid], marked: set[Oid], discard: bool = False):
        if commit in self._nextLocal:
            self._nextLocal.remove(commit)
            self._nextLocal.update(parents)
            if discard:
                marked.discard(commit)
        else:
            marked.add(commit)
