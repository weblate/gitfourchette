from gitfourchette import porcelain
from gitfourchette.stagingstate import StagingState
from gitfourchette.qt import *
from gitfourchette.tasks.repotask import RepoTask, TaskAffectsWhat, AbortIfDialogRejected, ReenterWhenDialogFinished
from gitfourchette.widgets.diffmodel import DiffModelError, DiffConflict, DiffModel, ShouldDisplayPatchAsImageDiff, \
    DiffImagePair
from gitfourchette import util
from html import escape
import os
import pygit2


class LoadWorkdirDiffs(RepoTask):
    def __init__(self, rw, allowUpdateIndex: bool):
        super().__init__(rw)
        self.dirtyDiff = None
        self.stageDiff = None
        self.allowUpdateIndex = allowUpdateIndex

    def name(self):
        return translate("Operation", "Refresh working directory")

    def execute(self):
        porcelain.refreshIndex(self.repo)
        self.dirtyDiff = porcelain.diffWorkdirToIndex(self.repo, self.allowUpdateIndex)
        self.stageDiff = porcelain.diffIndexToHead(self.repo)


class LoadCommit(RepoTask):
    def __init__(self, rw, oid: pygit2.Oid):
        super().__init__(rw)
        self.oid = oid
        self.diffs = None

    def name(self):
        return translate("Operation", "Load commit")

    def execute(self):
        # import time; time.sleep(1) #----------to debug out-of-order events
        self.diffs = porcelain.loadCommitDiffs(self.repo, self.oid)


class LoadPatch(RepoTask):
    def __init__(self, rw, patch: pygit2.Patch, stagingState: StagingState):
        super().__init__(rw)
        self.patch = patch
        self.stagingState = stagingState
        self.result = None

    def refreshWhat(self) -> TaskAffectsWhat:
        return TaskAffectsWhat.NOTHING  # let custom callback in RepoWidget do it

    def name(self):
        return translate("Operation", "Load diff")

    def _processPatch(self) -> DiffModel | DiffModelError | DiffConflict | DiffImagePair:
        patch = self.patch

        if not patch:
            return DiffModelError(
                self.tr("Patch is invalid."),
                self.tr("The patched file may have changed on disk since we last read it. Try refreshing the window."),
                icon=QStyle.StandardPixmap.SP_MessageBoxWarning)

        if patch.delta.status == pygit2.GIT_DELTA_CONFLICTED:
            ancestor, ours, theirs = self.repo.index.conflicts[patch.delta.new_file.path]
            return DiffConflict(self.repo, ancestor, ours, theirs)

        try:
            diffModel = DiffModel.fromPatch(patch)
            diffModel.document.moveToThread(QApplication.instance().thread())
            return diffModel
        except DiffModelError as dme:
            return dme
        except ShouldDisplayPatchAsImageDiff:
            return DiffImagePair(self.repo, patch.delta, self.stagingState)
        except BaseException as exc:
            summary, details = util.excStrings(exc)
            return DiffModelError(summary, icon=QStyle.StandardPixmap.SP_MessageBoxCritical, preformatted=details)

    def execute(self):
        self.result = self._processPatch()
