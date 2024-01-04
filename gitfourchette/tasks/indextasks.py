from gitfourchette import reverseunidiff
from gitfourchette.diffview.diffview import PatchPurpose
from gitfourchette.nav import NavLocator
from gitfourchette.porcelain import *
from gitfourchette.qt import *
from gitfourchette.tasks.repotask import RepoTask, TaskEffects
from gitfourchette.toolbox import *
from gitfourchette.trash import Trash
from gitfourchette.unmergedconflict import UnmergedConflict
import os


class _BaseStagingTask(RepoTask):
    def canKill(self, task: 'RepoTask'):
        # Jump/Refresh tasks shouldn't prevent a staging task from starting
        # when the user holds down RETURN/DELETE in a FileListView
        # to stage/unstage a series of files.
        from gitfourchette import tasks
        return isinstance(task, (tasks.Jump, tasks.RefreshRepo))

    def effects(self):
        return TaskEffects.Workdir | TaskEffects.ShowWorkdir


class StageFiles(_BaseStagingTask):
    def flow(self, patches: list[Patch]):
        if not patches:  # Nothing to stage (may happen if user keeps pressing Enter in file list view)
            QApplication.beep()
            yield from self.flowAbort()

        yield from self.flowEnterWorkerThread()
        self.repo.stage_files(patches)


class DiscardFiles(_BaseStagingTask):
    def effects(self):
        return TaskEffects.Workdir

    def flow(self, patches: list[Patch]):
        textPara = []

        verb = self.tr("Discard changes", "Button label")

        if not patches:  # Nothing to discard (may happen if user keeps pressing Delete in file list view)
            QApplication.beep()
            yield from self.flowAbort()
        elif len(patches) == 1:
            patch = patches[0]
            path = patch.delta.new_file.path
            if patch.delta.status == GIT_DELTA_UNTRACKED:
                textPara.append(self.tr("Really delete <b>“{0}”</b>?").format(escape(path)))
                verb = self.tr("Delete file", "Button label")
            else:
                textPara.append(self.tr("Really discard changes to <b>“{0}”</b>?").format(escape(path)))
        else:
            textPara.append(self.tr("Really discard changes to <b>%n files</b>?", "", len(patches)))
        textPara.append(translate("Global", "This cannot be undone!"))

        yield from self.flowConfirm(
            text=paragraphs(textPara),
            verb=verb,
            buttonIcon=QStyle.StandardPixmap.SP_DialogDiscardButton)

        yield from self.flowEnterWorkerThread()
        paths = [patch.delta.new_file.path for patch in patches]
        Trash(self.repo).backupPatches(patches)
        self.repo.restore_files_from_index(paths)


class UnstageFiles(_BaseStagingTask):
    def flow(self, patches: list[Patch]):
        if not patches:  # Nothing to unstage (may happen if user keeps pressing Delete in file list view)
            QApplication.beep()
            yield from self.flowAbort()

        yield from self.flowEnterWorkerThread()
        self.repo.unstage_files(patches)


class DiscardModeChanges(_BaseStagingTask):
    def flow(self, patches: list[Patch]):
        textPara = []

        if not patches:  # Nothing to unstage (may happen if user keeps pressing Delete in file list view)
            QApplication.beep()
            yield from self.flowAbort()
        elif len(patches) == 1:
            path = patches[0].delta.new_file.path
            textPara.append(self.tr("Really discard mode change in <b>“{0}”</b>?").format(escape(path)))
        else:
            textPara.append(self.tr("Really discard mode changes in <b>%n files</b>?", "", len(patches)))
        textPara.append(translate("Global", "This cannot be undone!"))

        yield from self.flowConfirm(
            text=paragraphs(textPara),
            verb=self.tr("Discard mode changes", "Button label"),
            buttonIcon=QStyle.StandardPixmap.SP_DialogDiscardButton)

        yield from self.flowEnterWorkerThread()
        paths = [patch.delta.new_file.path for patch in patches]
        self.repo.discard_mode_changes(paths)


class UnstageModeChanges(_BaseStagingTask):
    def flow(self, patches: list[Patch]):
        if not patches:  # Nothing to unstage (may happen if user keeps pressing Delete in file list view)
            QApplication.beep()
            yield from self.flowAbort()

        yield from self.flowEnterWorkerThread()
        self.repo.unstage_mode_changes(patches)


class ApplyPatch(RepoTask):
    def effects(self) -> TaskEffects:
        # Patched file stays dirty
        # TODO: Show Patched File In Workdir
        return TaskEffects.Workdir | TaskEffects.ShowWorkdir

    def flow(self, fullPatch: Patch, subPatch: bytes, purpose: PatchPurpose):
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
            yield from self.flowConfirm(
                title,
                text=paragraphs(textPara),
                verb=title,
                buttonIcon=QStyle.StandardPixmap.SP_DialogDiscardButton)

            Trash(self.repo).backupPatch(subPatch, fullPatch.delta.new_file.path)
            applyLocation = GIT_APPLY_LOCATION_WORKDIR
        else:
            applyLocation = GIT_APPLY_LOCATION_INDEX

        yield from self.flowEnterWorkerThread()
        self.repo.apply(subPatch, applyLocation)

    def _applyFullPatch(self, fullPatch: Patch, purpose: PatchPurpose):
        action = PatchPurpose.getName(purpose)
        verb = PatchPurpose.getName(purpose, verbOnly=True).lower()
        shortPath = os.path.basename(fullPatch.delta.new_file.path)

        questionText = paragraphs(
            self.tr("You are trying to {0} changes from the line-by-line editor, but you haven’t selected any red/green lines.").format(verb),
            self.tr("Do you want to {0} this entire file <b>“{1}”</b>?").format(verb, escape(shortPath)))

        qmb = asyncMessageBox(
            self.parentWidget(),
            'information',
            self.tr("{0}: selection empty").format(action),
            questionText,
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)

        applyButton: QPushButton = qmb.button(QMessageBox.StandardButton.Ok)
        applyButton.setText(self.tr("{0} entire &file").format(verb.title()))
        applyButton.setIcon(QIcon())

        # We want the user to pay attention here. Don't let them press enter to stage/unstage the entire file.
        qmb.setDefaultButton(QMessageBox.StandardButton.Cancel)
        yield from self.flowDialog(qmb)
        qmb.deleteLater()

        yield from self.flowEnterWorkerThread()
        if purpose & PatchPurpose.UNSTAGE:
            self.repo.unstage_files([fullPatch])
        elif purpose & PatchPurpose.STAGE:
            self.repo.stage_files([fullPatch])
        elif purpose & PatchPurpose.DISCARD:
            Trash(self.repo).backupPatches([fullPatch])
            self.repo.restore_files_from_index([fullPatch.delta.new_file.path])
        else:
            raise KeyError(f"applyFullPatch: unsupported purpose {purpose}")


class RevertPatch(RepoTask):
    def effects(self) -> TaskEffects:
        # Patched file stays dirty
        # TODO: Show Patched File In Workdir
        return TaskEffects.Workdir | TaskEffects.ShowWorkdir

    def flow(self, fullPatch: Patch, patchData: bytes):
        if not patchData:
            yield from self.flowAbort(self.tr("There’s nothing to revert in the selection."))

        diff = self.repo.applies_breakdown(patchData, location=GIT_APPLY_LOCATION_WORKDIR)
        if not diff:
            yield from self.flowAbort(
                self.tr("Couldn’t revert this patch.<br>The code may have diverged too much from this revision."))

        yield from self.flowEnterWorkerThread()
        diff = self.repo.apply(diff, location=GIT_APPLY_LOCATION_WORKDIR)

        # After the task, jump to a NavLocator that points to any file that was modified by the patch
        for p in diff:
            if p.delta.status != GIT_DELTA_DELETED:
                self.jumpTo = NavLocator.inUnstaged(p.delta.new_file.path)
                break


class HardSolveConflict(RepoTask):
    def effects(self) -> TaskEffects:
        return TaskEffects.Workdir

    def flow(self, path: str, keepOid: Oid):
        yield from self.flowEnterWorkerThread()
        repo = self.repo
        fullPath = os.path.join(repo.workdir, path)

        repo.refresh_index()
        assert (repo.index.conflicts is not None) and (path in repo.index.conflicts)

        trash = Trash(repo)
        trash.backupFile(path)

        # TODO: we should probably set the modes correctly and stuff as well
        if keepOid == NULL_OID:
            os.unlink(fullPath)
        else:
            blob = repo.peel_blob(keepOid)
            with open(fullPath, "wb") as f:
                f.write(blob.data)

        del repo.index.conflicts[path]
        assert (repo.index.conflicts is None) or (path not in repo.index.conflicts)

        if keepOid != NULL_OID:
            # Stage the file so it doesn't show up in both file lists
            repo.index.add(path)

            # Jump to staged file after the task
            self.jumpTo = NavLocator.inStaged(path)

        # Write index modifications to disk
        repo.index.write()


class MarkConflictSolved(RepoTask):
    def effects(self) -> TaskEffects:
        return TaskEffects.Workdir

    def flow(self, path: str):
        yield from self.flowEnterWorkerThread()
        repo = self.repo

        repo.refresh_index()
        assert (repo.index.conflicts is not None) and (path in repo.index.conflicts)

        del repo.index.conflicts[path]
        assert (repo.index.conflicts is None) or (path not in repo.index.conflicts)
        repo.index.write()


class AcceptMergeConflictResolution(RepoTask):
    def effects(self) -> TaskEffects:
        return TaskEffects.Workdir

    def flow(self, umc: UnmergedConflict):
        yield from self.flowEnterWorkerThread()
        repo = self.repo

        with open(umc.scratchPath, "rb") as scratchFile, \
                open(repo.in_workdir(umc.conflict.ours.path), "wb") as ourFile:
            data = scratchFile.read()
            ourFile.write(data)

        del repo.index.conflicts[umc.conflict.ours.path]
        repo.index.add(umc.conflict.ours.path)

        umc.deleteLater()


class ApplyPatchFile(RepoTask):
    def effects(self) -> TaskEffects:
        return TaskEffects.Workdir

    def flow(self, reverse: bool = False, path: str = ""):
        if reverse:
            title = self.tr("Import patch file (to apply in reverse)")
        else:
            title = self.tr("Import patch file")

        patchFileCaption = self.tr("Patch file")
        allFilesCaption = self.tr("All files")

        if not path:
            qfd = PersistentFileDialog.openFile(
                self.parentWidget(), "OpenPatch", title, filter=F"{patchFileCaption} (*.patch);;{allFilesCaption} (*)")

            yield from self.flowDialog(qfd)

            path = qfd.selectedFiles()[0]

        yield from self.flowEnterWorkerThread()

        with open(path, 'rt', encoding='utf-8') as patchFile:
            patchData = patchFile.read()

        # May raise:
        # - IOError
        # - GitError
        # - UnicodeDecodeError (if passing in a random binary file)
        # - KeyError ('no patch found')
        loadedDiff: Diff = Diff.parse_diff(patchData)

        # Reverse the patch if user wants to.
        if reverse:
            patchData = reverseunidiff.reverseUnidiff(loadedDiff.patch)
            loadedDiff: Diff = Diff.parse_diff(patchData)

        # Do a dry run first so we don't litter the workdir with a patch that failed halfway through.
        # If the patch doesn't apply, this raises a MultiFileError.
        diff = self.repo.applies_breakdown(patchData)
        deltas = list(diff.deltas)

        yield from self.flowEnterUiThread()

        numDeltas = len(deltas)
        numListed = min(numDeltas, 10)
        numUnlisted = numDeltas - numListed
        if reverse:
            text = self.tr("Patch file <b>“{0}”</b>, <b>reversed</b>, can be applied cleanly to your working directory.")
        else:
            text = self.tr("Patch file <b>“{0}”</b> can be applied cleanly to your working directory.")
        text = text.format(os.path.basename(path))
        text += " "
        text += self.tr("It will modify <b>%n</b> files:", "", numDeltas)
        text += ulList(f"({d.status_char()}) {escape(d.new_file.path)}" for d in deltas)
        yield from self.flowConfirm(title, text, verb=self.tr("Apply patch"))

        self.repo.apply(loadedDiff, GIT_APPLY_LOCATION_WORKDIR)


class ApplyPatchFileReverse(ApplyPatchFile):
    def flow(self, path: str = ""):
        yield from ApplyPatchFile.flow(self, reverse=True, path=path)


class AbortMerge(RepoTask):
    def effects(self) -> TaskEffects:
        return TaskEffects.DefaultRefresh

    def flow(self):
        if self.repo.state() != GIT_REPOSITORY_STATE_MERGE:
            yield from self.flowAbort(self.tr("No merge is in progress."), icon='information')

        try:
            abortList = self.repo.get_reset_merge_file_list()
        except ValueError:
            message = self.tr("The merge cannot be aborted right now "
                              "because you have files that are both staged and unstaged.")
            yield from self.flowAbort(message)

        message = paragraphs(
            self.tr("Do you want to abort the merge? All conflicts will be cleared "
                    "and all <b>staged</b> changes will be lost."),
            self.tr("%n files will be reset:", "", len(abortList)))
        message += ulList(abortList)
        yield from self.flowConfirm(text=message)

        yield from self.flowEnterUiThread()
        self.repo.reset_merge()
        self.repo.state_cleanup()
