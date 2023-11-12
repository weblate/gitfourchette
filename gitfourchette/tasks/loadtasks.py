import contextlib

from gitfourchette import log
from gitfourchette.diffview.diffdocument import DiffDocument
from gitfourchette.diffview.specialdiff import (ShouldDisplayPatchAsImageDiff, SpecialDiffError, DiffImagePair,
                                                DiffConflict)
from gitfourchette.nav import NavLocator, NavFlags
from gitfourchette.porcelain import *
from gitfourchette.qt import *
from gitfourchette.tasks.repotask import RepoTask, TaskEffects
from gitfourchette.toolbox import *

TAG = "LoadTasks"


class LoadWorkdir(RepoTask):
    def canKill(self, task: RepoTask):
        if type(task) is LoadWorkdir:
            log.warning(TAG, "LoadWorkdir is killing another LoadWorkdir. This is inefficient!")
            return True
        return type(task) in [LoadCommit, LoadPatch]

    def flow(self, allowWriteIndex: bool):
        yield from self._flowBeginWorkerThread()

        with Benchmark("LoadWorkdir/Index"):
            self.repo.refresh_index()

        yield from self._flowBeginWorkerThread()  # let task thread be interrupted here
        with Benchmark("LoadWorkdir/Staged"):
            self.stageDiff = self.repo.get_staged_changes()

        yield from self._flowBeginWorkerThread()  # let task thread be interrupted here
        with Benchmark("LoadWorkdir/Unstaged"):
            self.dirtyDiff = self.repo.get_unstaged_changes(allowWriteIndex)


class LoadCommit(RepoTask):
    def canKill(self, task: RepoTask):
        return type(task) in [LoadWorkdir, LoadCommit, LoadPatch]

    def flow(self, oid: Oid):
        yield from self._flowBeginWorkerThread()
        self.diffs = self.repo.commit_diffs(oid)
        self.message = self.repo.get_commit_message(oid)


class LoadPatch(RepoTask):
    def effects(self) -> TaskEffects:
        return TaskEffects.Nothing  # let custom callback in RepoWidget do it

    def canKill(self, task: RepoTask):
        return type(task) in [LoadPatch]

    def _processPatch(self, patch: Patch, locator: NavLocator
                      ) -> DiffDocument | SpecialDiffError | DiffConflict | DiffImagePair:
        if not patch:
            locator = locator.withExtraFlags(NavFlags.ForceRefreshWorkdir)
            message = locator.toHtml(self.tr("The file appears to have changed on disk since we cached it. "
                                             "[Try to refresh it.]"))
            return SpecialDiffError(self.tr("Outdated diff."), message,
                                    icon=QStyle.StandardPixmap.SP_MessageBoxWarning)

        if not patch.delta:
            # Rare libgit2 bug, should be fixed in 1.6.0
            return SpecialDiffError(self.tr("Patch has no delta!"), icon=QStyle.StandardPixmap.SP_MessageBoxWarning)

        if patch.delta.status == GIT_DELTA_CONFLICTED:
            ancestor, ours, theirs = self.repo.index.conflicts[patch.delta.new_file.path]
            return DiffConflict(ancestor, ours, theirs)

        submodule = None
        with (contextlib.suppress(KeyError),
              contextlib.suppress(ValueError),  # "submodule <whatever> has not been added yet" (GIT_EEXISTS)
              Benchmark("Submodule detection")
              ):
            submodule = self.repo.lookup_submodule(patch.delta.new_file.path)
        if submodule:
            return SpecialDiffError.submoduleDiff(self.repo, submodule, patch)

        try:
            diffModel = DiffDocument.fromPatch(patch, locator)
            diffModel.document.moveToThread(QApplication.instance().thread())
            return diffModel
        except SpecialDiffError as dme:
            return dme
        except ShouldDisplayPatchAsImageDiff:
            return DiffImagePair(self.repo, patch.delta, locator)
        except BaseException as exc:
            summary, details = excStrings(exc)
            return SpecialDiffError(summary, icon=QStyle.StandardPixmap.SP_MessageBoxCritical, preformatted=details)

    def flow(self, patch: Patch, locator: NavLocator):
        yield from self._flowBeginWorkerThread()
        self.result = self._processPatch(patch, locator)
