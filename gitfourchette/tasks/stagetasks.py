from gitfourchette import porcelain
from gitfourchette import util
from gitfourchette.qt import *
from gitfourchette.tasks.repotask import RepoTask, TaskAffectsWhat
from gitfourchette.trash import Trash
from html import escape
import os
import pygit2


class _BaseStagingTask(RepoTask):
    @property
    def rw(self) -> 'RepoWidget':  # hack for now - assume parent is a RepoWidget
        return self.parent()

    def refreshWhat(self):
        return TaskAffectsWhat.INDEX


class StageFiles(_BaseStagingTask):
    def name(self):
        return translate("Operation", "Stage files")

    def flow(self, patches: list[pygit2.Patch]):
        yield from self._flowBeginWorkerThread()
        with self.rw.fileWatcher.blockWatchingIndex():  # TODO: Also block FSW from watching ALL changes
            porcelain.stageFiles(self.repo, patches)


class DiscardFiles(_BaseStagingTask):
    def name(self):
        return translate("Operation", "Discard files")

    def flow(self, patches: list[pygit2.Patch]):
        if len(patches) == 1:
            path = patches[0].delta.new_file.path
            text = self.tr("Really discard changes to <b>“{0}”</b>?").format(escape(path))
        else:
            text = self.tr("Really discard changes to <b>%n files</b>?", "", len(patches))
        text += "<br>" + translate("Global", "This cannot be undone!")

        yield from self._flowConfirm(self.tr("Discard changes"), text, QStyle.StandardPixmap.SP_DialogDiscardButton)

        yield from self._flowBeginWorkerThread()
        paths = [patch.delta.new_file.path for patch in patches]
        # TODO: block FSW from watching changes?
        Trash(self.repo).backupPatches(patches)
        porcelain.discardFiles(self.repo, paths)


class UnstageFiles(_BaseStagingTask):
    def name(self):
        return translate("Operation", "Unstage files")

    def flow(self, patches: list[pygit2.Patch]):
        yield from self._flowBeginWorkerThread()
        with self.rw.fileWatcher.blockWatchingIndex():
            porcelain.unstageFiles(self.repo, patches)


class HardSolveConflict(RepoTask):
    def name(self):
        return translate("Operation", "Hard solve conflict")

    def refreshWhat(self) -> TaskAffectsWhat:
        return TaskAffectsWhat.INDEX

    def flow(self, path: str, keepOid: pygit2.Oid):
        yield from self._flowBeginWorkerThread()
        repo = self.repo

        porcelain.refreshIndex(repo)
        assert (repo.index.conflicts is not None) and (path in repo.index.conflicts)

        trash = Trash(repo)
        trash.backupFile(path)

        # TODO: we should probably set the modes correctly and stuff as well
        blob: pygit2.Blob = repo[keepOid].peel(pygit2.Blob)
        with open(os.path.join(repo.workdir, path), "wb") as f:
            f.write(blob.data)

        del repo.index.conflicts[path]
        assert (repo.index.conflicts is None) or (path not in repo.index.conflicts)
        repo.index.write()


class MarkConflictSolved(RepoTask):
    def name(self):
        return translate("Operation", "Mark conflict solved")

    def refreshWhat(self) -> TaskAffectsWhat:
        return TaskAffectsWhat.INDEX

    def flow(self, path: str):
        yield from self._flowBeginWorkerThread()
        repo = self.repo

        porcelain.refreshIndex(repo)
        assert (repo.index.conflicts is not None) and (path in repo.index.conflicts)

        del repo.index.conflicts[path]
        assert (repo.index.conflicts is None) or (path not in repo.index.conflicts)
        repo.index.write()
