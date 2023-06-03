import enum
import pygit2


class HiddenCommitSolver:
    @enum.unique
    class Tag(enum.IntEnum):
        NONE = 0
        SOFTHIDE = 1
        HARDHIDE = 2
        SHOW = 3

    def __init__(self):
        self.tags = {}
        self.marked = set()

    def tagCommit(self, commit: pygit2.Oid, tag: Tag):
        self.tags[commit] = tag

    @property
    def done(self):
        return len(self.tags) == 0

    def feed(self, commit: pygit2.Oid, parents: list[pygit2.Oid]):
        T = HiddenCommitSolver.Tag
        tag = self.tags.pop(commit, T.NONE)

        if tag in [T.SOFTHIDE, T.HARDHIDE]:
            self.marked.add(commit)
            for p in parents:
                if p not in self.tags:
                    self.tags[p] = T.SOFTHIDE
        else:
            for p in parents:
                ctag = self.tags.get(p, T.NONE)
                if ctag != T.HARDHIDE:
                    self.tags[p] = T.SHOW


class ForeignCommitSolver:
    def __init__(self, commitsToRefs):
        self._nextLocal = set()
        self.marked = set()
        for commitOid, refList in commitsToRefs.items():
            if any(name == 'HEAD' or name.startswith("refs/heads/") for name in refList):
                self._nextLocal.add(commitOid)

    def setLocal(self, commit: pygit2.Oid):
        self._nextLocal.add(commit)

    def feed(self, commit: pygit2.Oid, parents: list[pygit2.Oid]):
        if commit in self._nextLocal:
            self._nextLocal.remove(commit)
            for p in parents:
                self._nextLocal.add(p)
        else:
            self.marked.add(commit)
