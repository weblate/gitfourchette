import enum
import pygit2


@enum.unique
class SolverTags(enum.IntEnum):
    MAYBE_HIDE = 1
    FORCE_HIDE = 2
    FORCE_SHOW = 3


class HiddenCommitSolver:
    def __init__(self):
        self._tags = {}
        self.hiddenCommits = set()

    def tagCommit(self, c, tag):
        self._tags[c] = tag

    def hideCommit(self, oid, force=False):
        if force:
            self._tags[oid] = SolverTags.FORCE_HIDE
        else:
            self._tags[oid] = SolverTags.MAYBE_HIDE

    @property
    def done(self):
        return len(self._tags) == 0

    def feedSequence(self, commitSequence: list):
        for commit in commitSequence:
            self.feed(commit)

    def feed(self, commit: pygit2.Commit):
        tag = self._tags.pop(commit.oid, '')

        if tag in [SolverTags.MAYBE_HIDE, SolverTags.FORCE_HIDE]:
            self.hiddenCommits.add(commit.oid)
            for p in commit.parents:
                pk = p.oid
                if pk not in self._tags:
                    self._tags[pk] = SolverTags.MAYBE_HIDE
        else:
            for p in commit.parents:
                pk = p.oid
                ctag = self._tags.get(pk, '')
                if ctag != SolverTags.FORCE_HIDE:
                    self._tags[pk] = SolverTags.FORCE_SHOW
