from gitfourchette import porcelain
from gitfourchette import util
from gitfourchette.qt import *
from gitfourchette.tasks.repotask import RepoTask, TaskAffectsWhat
from gitfourchette.trash import Trash
from gitfourchette.widgets.diffview import PatchPurpose
from html import escape
import os
import pygit2


class _BaseStagingTask(RepoTask):
    @property
    def rw(self) -> 'RepoWidget':  # hack for now - assume parent is a RepoWidget
        return self.parent()

    def refreshWhat(self):
        return TaskAffectsWhat.INDEX | TaskAffectsWhat.INDEXWRITE


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

    def refreshWhat(self):
        return TaskAffectsWhat.INDEX

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


class ApplyPatch(RepoTask):
    def name(self):
        return translate("Operation", "Apply patch")

    def refreshWhat(self) -> TaskAffectsWhat:
        return TaskAffectsWhat.INDEX | TaskAffectsWhat.INDEXWRITE

    def flow(self, fullPatch: pygit2.Patch, subPatch: bytes, purpose: PatchPurpose):
        if not subPatch:
            yield from self._applyFullPatch(fullPatch, purpose)
            return

        if purpose & PatchPurpose.DISCARD:
            title = PatchPurpose.getVerb(purpose)
            if purpose & PatchPurpose.HUNK:
                really = self.tr("Really discard this hunk?")
            else:
                really = self.tr("Really discard the selected lines?")
            really += "<br>" + translate("Global", "This cannot be undone!")
            yield from self._flowConfirm(
                title,
                really,
                acceptButtonIcon=QStyle.StandardPixmap.SP_DialogDiscardButton,
                acceptButtonText=title)

            Trash(self.repo).backupPatch(subPatch, fullPatch.delta.new_file.path)
            applyLocation = pygit2.GIT_APPLY_LOCATION_WORKDIR
        else:
            applyLocation = pygit2.GIT_APPLY_LOCATION_INDEX

        yield from self._flowBeginWorkerThread()
        porcelain.applyPatch(self.repo, subPatch, applyLocation)

    def _applyFullPatch(self, fullPatch: pygit2.Patch, purpose: PatchPurpose):
        verb = PatchPurpose.getVerb(purpose)

        qmb = util.asyncMessageBox(
            self.parent(),
            'information',
            self.tr("{0}: selection empty").format(verb),
            self.tr("You haven’t selected any red/green lines for {0}.").format(verb),
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Apply)

        applyButton: QPushButton = qmb.button(QMessageBox.StandardButton.Apply)
        applyButton.setText(self.tr("{0} entire &file").format(PatchPurpose.getVerb(purpose & 0b111)))
        applyButton.setIcon(QIcon())

        qmb.setEscapeButton(QMessageBox.StandardButton.Ok)
        qmb.show()
        yield from self._flowDialog(qmb)

        qmb.deleteLater()
        if qmb.result() != QMessageBox.StandardButton.Apply:
            yield from self._flowAbort()

        yield from self._flowBeginWorkerThread()
        if purpose & PatchPurpose.UNSTAGE:
            porcelain.unstageFiles(self.repo, [fullPatch])
        elif purpose & PatchPurpose.STAGE:
            porcelain.stageFiles(self.repo, [fullPatch])
        elif purpose & PatchPurpose.DISCARD:
            Trash(self.repo).backupPatches([fullPatch])
            porcelain.discardFiles(self.repo, [fullPatch.delta.new_file.path])
        else:
            raise KeyError(f"applyEntirePatch: unsupported purpose {purpose}")


class RevertPatch(RepoTask):
    def name(self):
        return translate("Operation", "Revert patch")

    def flow(self, fullPatch: pygit2.Patch, patchData: bytes):
        if not patchData:
            yield from self._flowAbort(self.tr("There’s nothing to revert in the selection."))

        diff = porcelain.patchApplies(self.repo, patchData, location=pygit2.GIT_APPLY_LOCATION_WORKDIR)
        if not diff:
            yield from self._flowAbort(
                self.tr("Couldn’t revert this patch.<br>The code may have diverged too much from this revision."))

        yield from self._flowBeginWorkerThread()
        diff = porcelain.applyPatch(self.repo, diff, location=pygit2.GIT_APPLY_LOCATION_WORKDIR)

        # yield from self._flowExitWorkerThread()
        # # Get any file changed by the diff
        # changedFile = ""
        # for p in diff:
        #     if p.delta.status != pygit2.GIT_DELTA_DELETED:
        #         changedFile = p.delta.new_file.path
        # self.patchApplied.emit(NavPos("UNSTAGED", changedFile))  # send a NavPos to have RepoWidget show the file in the unstaged list


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
