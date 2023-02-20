from gitfourchette import porcelain
from gitfourchette.qt import *
from gitfourchette.tasks.repotask import RepoTask, TaskAffectsWhat, AbortIfDialogRejected
from gitfourchette.trash import Trash
from gitfourchette import util
from html import escape
import os
import pygit2


class _BaseStagingTask(RepoTask):
    def __init__(self, rw: 'RepoWidget', patches: list[pygit2.Patch]):
        super().__init__(rw)
        self.patches = patches

    def refreshWhat(self):
        return TaskAffectsWhat.INDEX


class StageFiles(_BaseStagingTask):
    def name(self):
        numPatches = len(self.patches)
        return translate("Operation", "Stage %n file(s)", "", numPatches)

    def execute(self):
        with self.rw.fileWatcher.blockWatchingIndex():  # TODO: Also block FSW from watching ALL changes
            porcelain.stageFiles(self.repo, self.patches)


class DiscardFiles(_BaseStagingTask):
    def name(self):
        numPatches = len(self.patches)
        return translate("Operation", "Discard %n file(s)", "", numPatches)

    def preExecuteUiFlow(self):
        if len(self.patches) == 1:
            path = self.patches[0].delta.new_file.path
            text = self.tr("Really discard changes to <b>“{0}”</b>?").format(escape(path))
        else:
            text = self.tr("Really discard changes to <b>%n files</b>?", "", len(self.patches))
        text += "<br>" + translate("Global", "This cannot be undone!")

        yield self.abortIfQuestionRejected(self.tr("Discard changes"), text,
                                           QStyle.StandardPixmap.SP_DialogDiscardButton)

    def execute(self):
        paths = [patch.delta.new_file.path for patch in self.patches]
        # TODO: block FSW from watching changes?
        Trash(self.repo).backupPatches(self.patches)
        porcelain.discardFiles(self.repo, paths)


class UnstageFiles(_BaseStagingTask):
    def name(self):
        numPatches = len(self.patches)
        return translate("Operation", "Unstage %n file(s)", "", numPatches)

    def execute(self):
        with self.rw.fileWatcher.blockWatchingIndex():
            porcelain.unstageFiles(self.repo, self.patches)


class HardSolveConflict(RepoTask):
    def __init__(self, rw, path: str, keepOid: pygit2.Oid):
        super().__init__(rw)
        self.path = path
        self.keepOid = keepOid

    def name(self):
        return translate("Operation", "Hard solve conflict")

    def refreshWhat(self) -> TaskAffectsWhat:
        return TaskAffectsWhat.INDEX

    def execute(self):
        repo = self.repo
        path = self.path

        porcelain.refreshIndex(repo)
        assert (repo.index.conflicts is not None) and (path in repo.index.conflicts)

        trash = Trash(repo)
        trash.backupFile(path)

        # TODO: we should probably set the modes correctly and stuff as well
        blob: pygit2.Blob = repo[self.keepOid].peel(pygit2.Blob)
        with open(os.path.join(repo.workdir, path), "wb") as f:
            f.write(blob.data)

        del repo.index.conflicts[path]
        assert (repo.index.conflicts is None) or (path not in repo.index.conflicts)
        repo.index.write()


class MarkConflictSolved(RepoTask):
    def __init__(self, rw, path: str):
        super().__init__(rw)
        self.path = path

    def name(self):
        return translate("Operation", "Mark conflict solved")

    def refreshWhat(self) -> TaskAffectsWhat:
        return TaskAffectsWhat.INDEX

    def execute(self):
        repo = self.repo
        path = self.path

        porcelain.refreshIndex(repo)
        assert (repo.index.conflicts is not None) and (path in repo.index.conflicts)

        del repo.index.conflicts[path]
        assert (repo.index.conflicts is None) or (path not in repo.index.conflicts)
        repo.index.write()
