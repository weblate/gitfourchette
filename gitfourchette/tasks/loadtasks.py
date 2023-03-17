from gitfourchette import log
from gitfourchette import porcelain
from gitfourchette import util
from gitfourchette.benchmark import Benchmark
from gitfourchette.nav import NavLocator
from gitfourchette.qt import *
from gitfourchette.tasks.repotask import RepoTask, TaskAffectsWhat
from gitfourchette.widgets.diffmodel import DiffModelError, DiffConflict, DiffModel, ShouldDisplayPatchAsImageDiff, \
    DiffImagePair
import pygit2

TAG = "LoadTasks"


class LoadWorkdir(RepoTask):
    def name(self):
        return translate("Operation", "Refresh working directory")

    def canKill(self, task: RepoTask):
        if type(task) is LoadWorkdir:
            log.warning(TAG, "LoadWorkdir is killing another LoadWorkdir. This is inefficient!")
            return True
        return type(task) in [LoadCommit, LoadPatch]

    def flow(self, allowUpdateIndex: bool):
        yield from self._flowBeginWorkerThread()

        with Benchmark("LoadWorkdir/Index"):
            porcelain.refreshIndex(self.repo, force=allowUpdateIndex)

        yield from self._flowBeginWorkerThread()  # let task thread be interrupted here
        with Benchmark("LoadWorkdir/Staged"):
            self.stageDiff = porcelain.getStagedChanges(self.repo)

        yield from self._flowBeginWorkerThread()  # let task thread be interrupted here
        with Benchmark("LoadWorkdir/Unstaged"):
            self.dirtyDiff = porcelain.getUnstagedChanges(self.repo, allowUpdateIndex)


class LoadCommit(RepoTask):
    def name(self):
        return translate("Operation", "Load commit")

    def canKill(self, task: RepoTask):
        return type(task) in [LoadWorkdir, LoadCommit, LoadPatch]

    def flow(self, oid: pygit2.Oid):
        yield from self._flowBeginWorkerThread()
        # import time; time.sleep(1) #----------to debug out-of-order events
        self.diffs = porcelain.loadCommitDiffs(self.repo, oid)
        self.message = porcelain.getCommitMessage(self.repo, oid)


class LoadPatch(RepoTask):
    def refreshWhat(self) -> TaskAffectsWhat:
        return TaskAffectsWhat.NOTHING  # let custom callback in RepoWidget do it

    def name(self):
        return translate("Operation", "Load diff")

    def canKill(self, task: RepoTask):
        return type(task) in [LoadPatch]

    def _processPatch(self, patch: pygit2.Patch, locator: NavLocator
                      ) -> DiffModel | DiffModelError | DiffConflict | DiffImagePair:
        if not patch:
            return DiffModelError(
                self.tr("Patch is invalid."),
                self.tr("The patched file may have changed on disk since we cached it. "
                        "Try [refreshing] the window.").replace("[", "<a href='gitfourchette://refresh'>").replace("]", "</a>"),
            icon=QStyle.StandardPixmap.SP_MessageBoxWarning)

        if not patch.delta:
            # Rare libgit2 bug, should be fixed in 1.6.0
            return DiffModelError(self.tr("Patch has no delta!"), icon=QStyle.StandardPixmap.SP_MessageBoxWarning)

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
            return DiffImagePair(self.repo, patch.delta, locator)
        except BaseException as exc:
            summary, details = util.excStrings(exc)
            return DiffModelError(summary, icon=QStyle.StandardPixmap.SP_MessageBoxCritical, preformatted=details)

    def flow(self, patch: pygit2.Patch, locator: NavLocator):
        yield from self._flowBeginWorkerThread()
        # import time; time.sleep(1) #----------to debug out-of-order events
        self.result = self._processPatch(patch, locator)
