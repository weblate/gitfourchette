from gitfourchette import porcelain
from gitfourchette import reverseunidiff
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
        if not patches:  # Nothing to stage (may happen if user keeps pressing Enter in file list view)
            QApplication.beep()
            yield from self._flowAbort()

        yield from self._flowBeginWorkerThread()
        with self.rw.fileWatcher.blockWatchingIndex():  # TODO: Also block FSW from watching ALL changes
            porcelain.stageFiles(self.repo, patches)


class DiscardFiles(_BaseStagingTask):
    def name(self):
        return translate("Operation", "Discard files")

    def refreshWhat(self):
        return TaskAffectsWhat.INDEX

    def flow(self, patches: list[pygit2.Patch]):
        textPara = []

        if not patches:  # Nothing to discard (may happen if user keeps pressing Delete in file list view)
            QApplication.beep()
            yield from self._flowAbort()
        elif len(patches) == 1:
            path = patches[0].delta.new_file.path
            textPara.append(self.tr("Really discard changes to <b>“{0}”</b>?").format(escape(path)))
        else:
            textPara.append(self.tr("Really discard changes to <b>%n files</b>?", "", len(patches)))
        textPara.append(translate("Global", "This cannot be undone!"))

        yield from self._flowConfirm(
            text=util.paragraphs(textPara),
            verb=self.tr("Discard changes", "Button label"),
            buttonIcon=QStyle.StandardPixmap.SP_DialogDiscardButton)

        yield from self._flowBeginWorkerThread()
        paths = [patch.delta.new_file.path for patch in patches]
        # TODO: block FSW from watching changes?
        Trash(self.repo).backupPatches(patches)
        porcelain.discardFiles(self.repo, paths)


class UnstageFiles(_BaseStagingTask):
    def name(self):
        return translate("Operation", "Unstage files")

    def flow(self, patches: list[pygit2.Patch]):
        if not patches:  # Nothing to unstage (may happen if user keeps pressing Delete in file list view)
            QApplication.beep()
            yield from self._flowAbort()

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
            title = PatchPurpose.getName(purpose)
            textPara = []
            if purpose & PatchPurpose.HUNK:
                textPara.append(self.tr("Really discard this hunk?"))
            else:
                textPara.append(self.tr("Really discard the selected lines?"))
            textPara.append(translate("Global", "This cannot be undone!"))
            yield from self._flowConfirm(
                title,
                text=util.paragraphs(textPara),
                verb=self.tr("Discard lines", "Button label"),
                buttonIcon=QStyle.StandardPixmap.SP_DialogDiscardButton)

            Trash(self.repo).backupPatch(subPatch, fullPatch.delta.new_file.path)
            applyLocation = pygit2.GIT_APPLY_LOCATION_WORKDIR
        else:
            applyLocation = pygit2.GIT_APPLY_LOCATION_INDEX

        yield from self._flowBeginWorkerThread()
        porcelain.applyPatch(self.repo, subPatch, applyLocation)

    def _applyFullPatch(self, fullPatch: pygit2.Patch, purpose: PatchPurpose):
        action = PatchPurpose.getName(purpose)
        verb = PatchPurpose.getName(purpose, verbOnly=True).lower()
        shortPath = os.path.basename(fullPatch.delta.new_file.path)

        questionText = util.paragraphs(
            self.tr("You are trying to {0} changes from the line-by-line editor, but you haven’t selected any red/green lines.").format(verb),
            self.tr("Do you want to {0} this entire file <b>“{1}”</b>?").format(verb, escape(shortPath)))

        qmb = util.asyncMessageBox(
            self.parent(),
            'information',
            self.tr("{0}: selection empty").format(action),
            questionText,
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)

        applyButton: QPushButton = qmb.button(QMessageBox.StandardButton.Ok)
        applyButton.setText(self.tr("{0} entire &file").format(verb.title()))
        applyButton.setIcon(QIcon())

        # We want the user to pay attention here. Don't let them press enter to stage/unstage the entire file.
        qmb.setDefaultButton(QMessageBox.StandardButton.Cancel)
        qmb.show()
        yield from self._flowDialog(qmb)
        qmb.deleteLater()

        yield from self._flowBeginWorkerThread()
        if purpose & PatchPurpose.UNSTAGE:
            porcelain.unstageFiles(self.repo, [fullPatch])
        elif purpose & PatchPurpose.STAGE:
            porcelain.stageFiles(self.repo, [fullPatch])
        elif purpose & PatchPurpose.DISCARD:
            Trash(self.repo).backupPatches([fullPatch])
            porcelain.discardFiles(self.repo, [fullPatch.delta.new_file.path])
        else:
            raise KeyError(f"applyFullPatch: unsupported purpose {purpose}")


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


class ApplyPatchFile(RepoTask):
    def name(self):
        return translate("Operation", "Apply patch file")

    def refreshWhat(self) -> TaskAffectsWhat:
        return TaskAffectsWhat.INDEX  # TODO: not really... more like the workdir

    def flow(self, reverse: bool):
        if reverse:
            title = self.tr("Import patch file (to apply in reverse)")
        else:
            title = self.tr("Import patch file")

        patchFileCaption = self.tr("Patch file")
        allFilesCaption = self.tr("All files")

        path, _ = util.PersistentFileDialog.getOpenFileName(
            self.parent(), "OpenPatch", title, filter=F"{patchFileCaption} (*.patch);;{allFilesCaption} (*)")

        if not path:
            yield from self._flowAbort()

        yield from self._flowBeginWorkerThread()

        with open(path, 'rt', encoding='utf-8') as patchFile:
            patchData = patchFile.read()

        # May raise: IOError, GitError,
        # UnicodeDecodeError (if passing in a random binary file), KeyError ('no patch found')
        loadedDiff: pygit2.Diff = porcelain.loadPatch(patchData)

        # Reverse the patch if user wants to.
        if reverse:
            patchData = reverseunidiff.reverseUnidiff(loadedDiff.patch)
            loadedDiff: pygit2.Diff = porcelain.loadPatch(patchData)

        # Do a dry run first so we don't litter the workdir with a patch that failed halfway through.
        # If the patch doesn't apply, this raises a MultiFileError.
        porcelain.patchApplies(self.repo, patchData)

        porcelain.applyPatch(self.repo, loadedDiff, pygit2.GIT_APPLY_LOCATION_WORKDIR)
