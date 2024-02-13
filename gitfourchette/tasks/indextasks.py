from contextlib import suppress
import os

from gitfourchette import reverseunidiff
from gitfourchette.nav import NavLocator
from gitfourchette.porcelain import *
from gitfourchette.qt import *
from gitfourchette.tasks.repotask import AbortTask, RepoTask, TaskEffects
from gitfourchette.toolbox import *
from gitfourchette.trash import Trash
from gitfourchette.trtables import TrTables
from gitfourchette.unmergedconflict import UnmergedConflict


class _BaseStagingTask(RepoTask):
    def canKill(self, task: RepoTask):
        # Jump/Refresh tasks shouldn't prevent a staging task from starting
        # when the user holds down RETURN/DELETE in a FileListView
        # to stage/unstage a series of files.
        from gitfourchette import tasks
        return isinstance(task, (tasks.Jump, tasks.RefreshRepo))

    def effects(self):
        return TaskEffects.Workdir | TaskEffects.ShowWorkdir

    def denyConflicts(self, patches: list[Patch], purpose: PatchPurpose):
        conflicts = [p for p in patches if p.delta.status == DeltaStatus.CONFLICTED]

        if not conflicts:
            return

        numPatches = len(patches)
        numConflicts = len(conflicts)

        if numPatches == numConflicts:
            intro = self.tr("You have selected %n merge conflicts that are still unsolved.", "", numConflicts)
        else:
            intro = self.tr("There are %n unsolved merge conflicts among your selection.", "", numConflicts)

        if purpose == PatchPurpose.STAGE:
            please = self.tr("Please fix it/them before staging:", "'it/them' refers to the selected merge conflicts", numConflicts)
        else:
            please = self.tr("Please fix it/them before discarding:", "'it/them' refers to the selected merge conflicts", numConflicts)

        message = paragraphs(intro, please)
        message += ulList(p.delta.new_file.path for p in conflicts)
        raise AbortTask(message)

    def anySubmodules(self, patches: list[Patch], purpose: PatchPurpose):
        submos = [p for p in patches if p.delta.new_file.mode == FileMode.COMMIT]
        return submos


class StageFiles(_BaseStagingTask):
    def flow(self, patches: list[Patch]):
        if not patches:  # Nothing to stage (may happen if user keeps pressing Enter in file list view)
            QApplication.beep()
            raise AbortTask()

        self.denyConflicts(patches, PatchPurpose.STAGE)

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
            raise AbortTask()

        self.denyConflicts(patches, PatchPurpose.DISCARD)

        submos = self.anySubmodules(patches, PatchPurpose.DISCARD)
        anySubmos = bool(submos)
        allSubmos = len(submos) == len(patches)
        really = ""

        if len(patches) == 1:
            patch = patches[0]
            bpath = bquo(patch.delta.new_file.path)
            if patch.delta.status == DeltaStatus.UNTRACKED:
                really = self.tr("Really delete {0}?", "delete an untracked file").format(bpath)
                really += " " + self.tr("(This file is untracked – it’s never been committed yet.)")
                verb = self.tr("Delete", "button label to delete an untracked file")
            elif patch.delta.new_file.mode == FileMode.COMMIT:
                really = self.tr("Really discard changes in submodule {0}?").format(bpath)
            else:
                really = self.tr("Really discard changes to {0}?", "to [a specific file]").format(bpath)
        else:
            nFiles = btag(self.tr("%n files", "(discard changes to) %n files", len(patches) - len(submos)))
            nSubmos = btag(self.tr("%n submodules", "(discard changes in) %n submodules", len(submos)))
            if allSubmos:
                really = self.tr("Really discard changes in {0}?", "in [n submodules]").format(nSubmos)
            elif anySubmos:
                really = self.tr("Really discard changes to {0} and in {1}?", "to [n files] and in [n submodules]").format(nFiles, nSubmos)
            else:
                really = self.tr("Really discard changes to {0}?", "to [n files]").format(nFiles)

        textPara.append(really)
        if anySubmos:
            submoPostamble = self.tr("Any uncommitted changes in %n submodules will be <b>cleared</b> "
                                     "and the submodules’ HEAD will be reset.", "", len(submos))
            textPara.append(submoPostamble)

        textPara.append(tr("This cannot be undone!"))
        text = paragraphs(textPara)

        yield from self.flowConfirm(text=text, verb=verb,
                                    buttonIcon=QStyle.StandardPixmap.SP_DialogDiscardButton)

        yield from self.flowEnterWorkerThread()

        # TODO: Actually reset submodules if any!
        paths = [patch.delta.new_file.path for patch in patches]
        Trash.instance().backupPatches(self.repo.workdir, patches)
        self.repo.restore_files_from_index(paths)


class UnstageFiles(_BaseStagingTask):
    def flow(self, patches: list[Patch]):
        if not patches:  # Nothing to unstage (may happen if user keeps pressing Delete in file list view)
            QApplication.beep()
            raise AbortTask()

        yield from self.flowEnterWorkerThread()
        self.repo.unstage_files(patches)


class DiscardModeChanges(_BaseStagingTask):
    def flow(self, patches: list[Patch]):
        textPara = []

        if not patches:  # Nothing to unstage (may happen if user keeps pressing Delete in file list view)
            QApplication.beep()
            raise AbortTask()
        elif len(patches) == 1:
            path = patches[0].delta.new_file.path
            textPara.append(self.tr("Really discard mode change in {0}?").format(bquo(path)))
        else:
            textPara.append(self.tr("Really discard mode changes in <b>%n files</b>?", "", len(patches)))
        textPara.append(tr("This cannot be undone!"))

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
            raise AbortTask()

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
            title = TrTables.patchPurpose(purpose)
            textPara = []
            if purpose & PatchPurpose.HUNK:
                textPara.append(self.tr("Really discard this hunk?"))
            else:
                textPara.append(self.tr("Really discard the selected lines?"))
            textPara.append(tr("This cannot be undone!"))
            yield from self.flowConfirm(
                title,
                text=paragraphs(textPara),
                verb=title,
                buttonIcon=QStyle.StandardPixmap.SP_DialogDiscardButton)

            Trash.instance().backupPatch(self.repo.workdir, subPatch, fullPatch.delta.new_file.path)
            applyLocation = ApplyLocation.WORKDIR
        else:
            applyLocation = ApplyLocation.INDEX

        yield from self.flowEnterWorkerThread()
        self.repo.apply(subPatch, applyLocation)

    def _applyFullPatch(self, fullPatch: Patch, purpose: PatchPurpose):
        action = TrTables.patchPurpose(purpose)
        verb = TrTables.patchPurpose(purpose & PatchPurpose.VERB_MASK).lower()
        shortPath = os.path.basename(fullPatch.delta.new_file.path)

        questionText = paragraphs(
            self.tr("You are trying to {0} changes from the line-by-line editor, "
                    "but you haven’t selected any red/green lines."),
            self.tr("Do you want to {0} this entire file {1}?")
        ).format(verb, bquo(shortPath))

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
            Trash.instance().backupPatches(self.repo.workdir, [fullPatch])
            self.repo.restore_files_from_index([fullPatch.delta.new_file.path])
        else:
            raise KeyError(f"applyFullPatch: unsupported purpose {purpose}")


class RevertPatch(RepoTask):
    def effects(self) -> TaskEffects:
        # Patched file stays dirty
        return TaskEffects.Workdir | TaskEffects.ShowWorkdir

    def flow(self, fullPatch: Patch, patchData: bytes):
        if not patchData:
            raise AbortTask(self.tr("There’s nothing to revert in the selection."))

        diff = self.repo.applies_breakdown(patchData, location=ApplyLocation.WORKDIR)
        if not diff:
            raise AbortTask(
                self.tr("Couldn’t revert this patch.<br>The code may have diverged too much from this revision."))

        yield from self.flowEnterWorkerThread()
        diff = self.repo.apply(diff, location=ApplyLocation.WORKDIR)

        # After the task, jump to a NavLocator that points to any file that was modified by the patch
        for p in diff:
            if p.delta.status != DeltaStatus.DELETED:
                self.jumpTo = NavLocator.inUnstaged(p.delta.new_file.path)
                break


class HardSolveConflicts(RepoTask):
    def effects(self) -> TaskEffects:
        return TaskEffects.Workdir

    def flow(self, conflictedFiles: dict[str, Oid]):
        yield from self.flowEnterWorkerThread()

        repo = self.repo
        repo.refresh_index()
        index = repo.index
        conflicts = index.conflicts
        assert conflicts is not None

        assert isinstance(conflictedFiles, dict)
        for path, keepOid in conflictedFiles.items():
            assert type(path) is str
            assert type(keepOid) is Oid
            assert path in conflicts

            with suppress(FileNotFoundError):  # ignore FileNotFoundError for DELETED_BY_US conflicts
                Trash.instance().backupFile(repo.workdir, path)

            fullPath = repo.in_workdir(path)

            # TODO: we should probably set the modes correctly and stuff as well
            if keepOid == NULL_OID:
                if os.path.isfile(fullPath):  # the file may not exist in DELETED_BY_BOTH conflicts
                    os.unlink(fullPath)
            else:
                blob = repo.peel_blob(keepOid)
                with open(fullPath, "wb") as f:
                    f.write(blob.data)

            del conflicts[path]
            assert path not in conflicts

            if keepOid != NULL_OID:
                # Stage the file so it doesn't show up in both file lists
                index.add(path)

                # Jump to staged file after the task
                self.jumpTo = NavLocator.inStaged(path)

        # Write index modifications to disk
        index.write()


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
    def canKill(self, task: RepoTask) -> bool:
        from gitfourchette.tasks import RefreshRepo, Jump
        return isinstance(task, (RefreshRepo, Jump))

    def isCritical(self) -> bool:
        """
        We can't control when this task is invoked -- it's invoked as soon as
        the merge program exits. If the RepoTaskRunner is busy, don't interrupt
        an active task and enqueue this one because we don't want to miss it.
        (For example: this task is invoked while RepoTaskRunner is busy with
        NewCommit because the commit dialog is open. Wait for NewCommit to
        complete before executing this task.)
        """
        return True

    def effects(self) -> TaskEffects:
        return TaskEffects.Workdir

    def flow(self, umc: UnmergedConflict):
        message = paragraphs(
            self.tr("It looks like you’ve resolved the merge conflict in {0}."),
            self.tr("Do you want to keep this resolution?")
        ).format(bquo(umc.conflict.ours.path))

        yield from self.flowConfirm(
            self.tr("Merge conflict resolved"), message,
            verb=self.tr("Confirm resolution"), cancelText=self.tr("Discard resolution"))

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
        if reverse:
            text = self.tr("Patch file {0}, <b>reversed</b>, can be applied cleanly to your working directory.")
        else:
            text = self.tr("Patch file {0} can be applied cleanly to your working directory.")
        text = text.format(bquoe(os.path.basename(path)))
        details = self.tr("It will modify <b>%n</b> files:", "", numDeltas)
        details += ulList(f"({d.status_char()}) {escape(d.new_file.path)}" for d in deltas)
        yield from self.flowConfirm(title, text, verb=self.tr("Apply patch"), detailText=details)

        self.repo.apply(loadedDiff, ApplyLocation.WORKDIR)


class ApplyPatchFileReverse(ApplyPatchFile):
    def flow(self, path: str = ""):
        yield from ApplyPatchFile.flow(self, reverse=True, path=path)


class AbortMerge(RepoTask):
    def effects(self) -> TaskEffects:
        return TaskEffects.DefaultRefresh

    def flow(self):
        isMerging = self.repo.state() == RepositoryState.MERGE
        isCherryPicking = self.repo.state() == RepositoryState.CHERRYPICK

        if not isMerging and not isCherryPicking:
            raise AbortTask(self.tr("No merge or cherry-pick is in progress."), icon='information')

        try:
            abortList = self.repo.get_reset_merge_file_list()
        except ValueError:
            message = self.tr("Cannot abort right now because you have files that are both staged and unstaged.")
            raise AbortTask(message)

        message = paragraphs(
            self.tr("Do you want to abort the merge?") if not isCherryPicking
            else self.tr("Do you want to abort the cherry-pick?"),
        )

        if not abortList:
            details = self.tr("No files are affected.")
        else:
            if self.repo.any_conflicts:
                message += paragraphs(self.tr("All conflicts will be cleared "
                                              "and all <b>staged</b> changes will be lost."))
            else:
                message += paragraphs(self.tr("All <b>staged</b> changes will be lost."))

            details = paragraphs(self.tr("%n files will be reset:", "", len(abortList)))
            details += "<span style='white-space: pre'>" + ulList(abortList)

        verb = self.tr("Abort merge") if isMerging else self.tr("Abort cherry-pick")

        yield from self.flowConfirm(text=message, verb=verb, detailText=details)

        yield from self.flowEnterUiThread()
        self.repo.reset_merge()
        self.repo.state_cleanup()
