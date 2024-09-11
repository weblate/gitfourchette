import logging
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

logger = logging.getLogger(__name__)


class _BaseStagingTask(RepoTask):
    def canKill(self, task: RepoTask):
        # Jump/Refresh tasks shouldn't prevent a staging task from starting
        # when the user holds down RETURN/DELETE in a FileListView
        # to stage/unstage a series of files.
        from gitfourchette import tasks
        return isinstance(task, tasks.Jump | tasks.RefreshRepo)

    def denyConflicts(self, patches: list[Patch], purpose: PatchPurpose):
        conflicts = [p for p in patches if p.delta.status == DeltaStatus.CONFLICTED]

        if not conflicts:
            return

        numPatches = len(patches)
        numConflicts = len(conflicts)

        if numPatches == numConflicts:
            intro = tr("You have selected %n merge conflicts that are still unsolved.", "", numConflicts)
        else:
            intro = tr("There are %n unsolved merge conflicts among your selection.", "", numConflicts)

        if purpose == PatchPurpose.STAGE:
            please = tr("Please fix it/them before staging:", "'it/them' refers to the selected merge conflicts", numConflicts)
        else:
            please = tr("Please fix it/them before discarding:", "'it/them' refers to the selected merge conflicts", numConflicts)

        message = paragraphs(intro, please)
        message += toTightUL(p.delta.new_file.path for p in conflicts)
        raise AbortTask(message)

    @staticmethod
    def filterSubmodules(patches: list[Patch]) -> list[Patch]:
        submos = [p for p in patches if SubmoduleDiff.is_submodule_patch(p)]
        return submos


class StageFiles(_BaseStagingTask):
    def flow(self, patches: list[Patch]):
        if not patches:  # Nothing to stage (may happen if user keeps pressing Enter in file list view)
            QApplication.beep()
            raise AbortTask()

        self.denyConflicts(patches, PatchPurpose.STAGE)

        yield from self.flowEnterWorkerThread()
        self.effects |= TaskEffects.Workdir

        self.repo.stage_files(patches)

        yield from self.debriefPostStage(patches)

        self.postStatus = self.tr("%n files staged.", "", len(patches))

    def debriefPostStage(self, patches: list[Patch]):
        debrief = {}

        for patch in patches:
            newFile: DiffFile = patch.delta.new_file
            m = ""

            if newFile.mode == FileMode.TREE:
                m = self.tr("You’ve added another Git repo inside your current repo. "
                            "You should absorb it as a submodule.")
            elif SubmoduleDiff.is_submodule_patch(patch):
                info = self.repo.get_submodule_diff(patch)
                if info.is_del:
                    m = self.tr("Don’t forget to remove the submodule from .gitmodules "
                                "to complete its deletion.")
                elif not info.is_trivially_indexable:
                    m = self.tr("Uncommitted changes in the submodule "
                                "can’t be staged from the parent repository.")

            if m:
                debrief[newFile.path] = m

        if not debrief:
            return

        # For better perceived responsivity, show message box asynchronously
        # so that RefreshRepo occurs in the background after the task completes
        yield from self.flowEnterUiThread()
        qmb = asyncMessageBox(
            self.parentWidget(),
            'information',
            self.name(),
            self.tr("%n items require your attention after staging:", "", len(debrief)))
        addULToMessageBox(qmb, [f"{btag(path)}: {issue}" for path, issue in debrief.items()])
        qmb.show()


class DiscardFiles(_BaseStagingTask):
    def flow(self, patches: list[Patch]):
        textPara = []

        verb = self.tr("Discard changes", "Button label")

        if not patches:  # Nothing to discard (may happen if user keeps pressing Delete in file list view)
            QApplication.beep()
            raise AbortTask()

        self.denyConflicts(patches, PatchPurpose.DISCARD)

        submos = self.filterSubmodules(patches)
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
                                    buttonIcon="SP_DialogDiscardButton")

        yield from self.flowEnterWorkerThread()
        self.effects |= TaskEffects.Workdir

        paths = [patch.delta.new_file.path for patch in patches
                 if patch not in submos]
        if paths:
            Trash.instance().backupPatches(self.repo.workdir, patches)
            self.repo.restore_files_from_index(paths)

        if submos:
            self.effects |= TaskEffects.Refs  # We don't have TaskEffects.Submodules so .Refs is the next best thing
            for patch in submos:
                self.restoreSubmodule(patch)

        self.postStatus = self.tr("%n files discarded.", "", len(patches))

    def restoreSubmodule(self, patch: Patch):
        path = patch.delta.new_file.path
        submodule = self.repo.submodules[path]

        if patch.delta.status == DeltaStatus.DELETED:
            didRestore = self.repo.restore_submodule_gitlink(path)
            if not didRestore:
                # TODO: more user-friendly error if couldn't restore?
                logger.warning(f"Couldn't restore gitlink for submodule {path}")

        with RepoContext(self.repo.in_workdir(path), RepositoryOpenFlag.NO_SEARCH) as subRepo:
            # Reset HEAD to the target commit
            subRepo.reset(submodule.head_id, ResetMode.HARD)
            # Nuke uncommitted files as well
            subRepo.checkout_head(strategy=CheckoutStrategy.REMOVE_UNTRACKED | CheckoutStrategy.FORCE | CheckoutStrategy.RECREATE_MISSING)
            # TODO: Recurse?


class UnstageFiles(_BaseStagingTask):
    def flow(self, patches: list[Patch]):
        if not patches:  # Nothing to unstage (may happen if user keeps pressing Delete in file list view)
            QApplication.beep()
            raise AbortTask()

        yield from self.flowEnterWorkerThread()
        self.effects |= TaskEffects.Workdir

        self.repo.unstage_files(patches)

        self.postStatus = self.tr("%n files unstaged.", "", len(patches))


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
            buttonIcon="SP_DialogDiscardButton")

        yield from self.flowEnterWorkerThread()
        self.effects |= TaskEffects.Workdir

        paths = [patch.delta.new_file.path for patch in patches]
        self.repo.discard_mode_changes(paths)


class UnstageModeChanges(_BaseStagingTask):
    def flow(self, patches: list[Patch]):
        if not patches:  # Nothing to unstage (may happen if user keeps pressing Delete in file list view)
            QApplication.beep()
            raise AbortTask()

        yield from self.flowEnterWorkerThread()
        self.effects |= TaskEffects.Workdir

        self.repo.unstage_mode_changes(patches)


class ApplyPatch(RepoTask):
    def flow(self, fullPatch: Patch, subPatch: bytes, purpose: PatchPurpose):
        if not subPatch:
            QApplication.beep()
            verb = TrTables.patchPurpose(purpose & PatchPurpose.VERB_MASK).lower()
            message = self.tr("Can’t {verb} the selection because no red/green lines are selected.").format(verb=verb)
            raise AbortTask(message, asStatusMessage=True)

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
                buttonIcon="SP_DialogDiscardButton")

            Trash.instance().backupPatch(self.repo.workdir, subPatch, fullPatch.delta.new_file.path)
            applyLocation = ApplyLocation.WORKDIR
        else:
            applyLocation = ApplyLocation.INDEX

        yield from self.flowEnterWorkerThread()
        self.effects |= TaskEffects.Workdir

        self.repo.apply(subPatch, applyLocation)

        self.postStatus = TrTables.patchPurposePastTense(purpose)


class RevertPatch(RepoTask):
    def flow(self, fullPatch: Patch, patchData: bytes):
        if not patchData:
            raise AbortTask(self.tr("There’s nothing to revert in the selection."))

        diff = self.repo.applies_breakdown(patchData, location=ApplyLocation.WORKDIR)
        if not diff:
            raise AbortTask(self.tr("Couldn’t revert this patch.") + "<br>" +
                            self.tr("The code may have diverged too much from this revision."))

        yield from self.flowEnterWorkerThread()
        self.effects |= TaskEffects.Workdir

        diff = self.repo.apply(diff, location=ApplyLocation.WORKDIR)

        # After the task, jump to a NavLocator that points to any file that was modified by the patch
        for p in diff:
            if p.delta.status != DeltaStatus.DELETED:
                self.jumpTo = NavLocator.inUnstaged(p.delta.new_file.path)
                break


class HardSolveConflicts(RepoTask):
    def flow(self, conflictedFiles: dict[str, Oid]):
        yield from self.flowEnterWorkerThread()
        self.effects |= TaskEffects.Workdir

        repo = self.repo
        repo.refresh_index()
        index = repo.index
        conflicts = index.conflicts
        assert conflicts is not None

        assert isinstance(conflictedFiles, dict)
        for path, keepId in conflictedFiles.items():
            assert type(path) is str
            assert type(keepId) is Oid
            assert path in conflicts

            with suppress(FileNotFoundError):  # ignore FileNotFoundError for DELETED_BY_US conflicts
                Trash.instance().backupFile(repo.workdir, path)

            fullPath = repo.in_workdir(path)

            # TODO: we should probably set the modes correctly and stuff as well
            if keepId == NULL_OID:
                if os.path.isfile(fullPath):  # the file may not exist in DELETED_BY_BOTH conflicts
                    os.unlink(fullPath)
            else:
                blob = repo.peel_blob(keepId)
                with open(fullPath, "wb") as f:
                    f.write(blob.data)

            del conflicts[path]
            assert path not in conflicts

            if keepId != NULL_OID:
                # Stage the file so it doesn't show up in both file lists
                index.add(path)

                # Jump to staged file after the task
                self.jumpTo = NavLocator.inStaged(path)

        # Write index modifications to disk
        index.write()


class MarkConflictSolved(RepoTask):
    def flow(self, path: str):
        yield from self.flowEnterWorkerThread()
        self.effects |= TaskEffects.Workdir

        repo = self.repo

        repo.refresh_index()
        assert (repo.index.conflicts is not None) and (path in repo.index.conflicts)

        del repo.index.conflicts[path]
        assert (repo.index.conflicts is None) or (path not in repo.index.conflicts)
        repo.index.write()


class AcceptMergeConflictResolution(RepoTask):
    def canKill(self, task: RepoTask) -> bool:
        from gitfourchette.tasks import RefreshRepo, Jump
        return isinstance(task, RefreshRepo | Jump)

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

    def flow(self, umc: UnmergedConflict):
        message = paragraphs(
            self.tr("It looks like you’ve resolved the merge conflict in {0}."),
            self.tr("Do you want to keep this resolution?")
        ).format(bquo(umc.conflict.ours.path))

        yield from self.flowConfirm(
            self.tr("Merge conflict resolved"), message,
            verb=self.tr("Confirm resolution"), cancelText=self.tr("Discard resolution"))

        yield from self.flowEnterWorkerThread()
        self.effects |= TaskEffects.Workdir

        repo = self.repo

        path = umc.conflict.ours.path
        with open(umc.scratchPath, "rb") as scratchFile, \
                open(repo.in_workdir(path), "wb") as ourFile:
            data = scratchFile.read()
            ourFile.write(data)

        del repo.index.conflicts[path]
        repo.index.add(path)

        # Jump to staged file after confirming conflict resolution
        self.jumpTo = NavLocator.inStaged(path)

        umc.deleteLater()


class ApplyPatchFile(RepoTask):
    def flow(self, reverse: bool = False, path: str = ""):
        if reverse:
            title = self.tr("Revert patch file")
            verb = self.tr("Revert")
        else:
            title = self.tr("Apply patch file")
            verb = self.tr("Apply")

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
        # - OSError
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
        text = self.tr("Do you want to {verb} patch file {path}?")
        text = text.format(path=bquoe(os.path.basename(path)), verb=tagify(verb.lower(), "<b>"))
        informative = self.tr("<b>%n</b> files will be modified in your working directory:", "", numDeltas)
        details = [f"({d.status_char()}) {escape(d.new_file.path)}" for d in deltas]
        yield from self.flowConfirm(title, text, verb=verb, informativeText=informative, detailList=details)

        self.effects |= TaskEffects.Workdir

        self.repo.apply(loadedDiff, ApplyLocation.WORKDIR)
        self.jumpTo = NavLocator.inUnstaged(deltas[0].new_file.path)


class ApplyPatchFileReverse(ApplyPatchFile):
    def flow(self, path: str = ""):
        yield from ApplyPatchFile.flow(self, reverse=True, path=path)


class ApplyPatchData(RepoTask):
    def flow(self, patchData: str, reverse: bool):
        yield from self.flowEnterWorkerThread()

        if reverse:
            patchData = reverseunidiff.reverseUnidiff(patchData)
        loadedDiff: Diff = Diff.parse_diff(patchData)

        # Do a dry run first so we don't litter the workdir with a patch that failed halfway through.
        # If the patch doesn't apply, this raises a MultiFileError.
        diff = self.repo.applies_breakdown(patchData)
        deltas = list(diff.deltas)

        yield from self.flowEnterUiThread()

        title = self.tr("Revert patch") if reverse else self.tr("Apply patch")
        verb = self.tr("Revert") if reverse else self.tr("Apply")

        numDeltas = len(deltas)
        text = self.tr("Do you want to {verb} this patch?")
        text = text.format(verb=tagify(verb.lower(), "<b>"))
        informative = self.tr("<b>%n</b> files will be modified in your working directory:", "", numDeltas)
        details = [f"({d.status_char()}) {escape(d.new_file.path)}" for d in deltas]
        yield from self.flowConfirm(title, text, verb=verb, informativeText=informative, detailList=details)

        self.effects |= TaskEffects.Workdir
        self.repo.apply(loadedDiff, ApplyLocation.WORKDIR)
        self.jumpTo = NavLocator.inUnstaged(deltas[0].new_file.path)


class RestoreRevisionToWorkdir(RepoTask):
    def flow(self, patch: Patch, old: bool):
        if old:
            preposition = self.tr("before", "preposition slotted into '...BEFORE this commit'")
            diffFile = patch.delta.old_file
            delete = patch.delta.status == DeltaStatus.ADDED
        else:
            preposition = self.tr("at", "preposition slotted into '...AT this commit'")
            diffFile = patch.delta.new_file
            delete = patch.delta.status == DeltaStatus.DELETED

        path = self.repo.in_workdir(diffFile.path)
        existsNow = os.path.isfile(path)

        if not existsNow and delete:
            message = self.tr("Your working copy of {path} already matches the revision {preposition} this commit.")
            message = message.format(path=bquo(diffFile.path), preposition=preposition)
            raise AbortTask(message, icon="information")

        if not existsNow:
            actionVerb = self.tr("recreated")
        elif delete:
            actionVerb = self.tr("deleted")
        else:
            actionVerb = self.tr("overwritten")
        prompt = paragraphs(
            self.tr("Do you want to restore {path} as it was {preposition} this commit?"),
            self.tr("This file will be {processed} in your working directory.")
        ).format(path=bquo(diffFile.path), preposition=preposition, processed=actionVerb)

        yield from self.flowConfirm(text=prompt, verb=self.tr("Restore"))

        self.effects |= TaskEffects.Workdir

        if delete:
            os.unlink(path)
        else:
            blob = self.repo.peel_blob(diffFile.id)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(blob.data)
            os.chmod(path, diffFile.mode)

        self.jumpTo = NavLocator.inUnstaged(diffFile.path)


class AbortMerge(RepoTask):
    def flow(self):
        self.repo.refresh_index()

        isMerging = self.repo.state() == RepositoryState.MERGE
        isCherryPicking = self.repo.state() == RepositoryState.CHERRYPICK
        isReverting = self.repo.state() == RepositoryState.REVERT
        anyConflicts = self.repo.index.conflicts

        if not (isMerging or isCherryPicking or isReverting or anyConflicts):
            raise AbortTask(self.tr("No abortable state is in progress."), icon='information')

        verb = self.tr("Abort")
        if isCherryPicking:
            clause = self.tr("abort the ongoing cherry-pick")
            title = self.tr("Abort cherry-pick")
        elif isMerging:
            clause = self.tr("abort the ongoing merge")
            title = self.tr("Abort merge")
        elif isReverting:
            clause = self.tr("abort the ongoing revert")
            title = self.tr("Abort revert")
        else:
            clause = self.tr("reset the index")
            title = self.tr("Reset index")

        try:
            abortList = self.repo.get_reset_merge_file_list()
        except MultiFileError as exc:
            exc.message = self.tr(
                "Cannot {0} right now, because %n files contain both staged and unstaged changes.",
                "placeholder: cannot abort the merge / reset the index / etc.", len(exc.file_exceptions)
            ).format(clause)
            raise exc

        lines = [self.tr("Do you want to {0}?").format(clause)]

        if not abortList:
            informative = self.tr("No files are affected.")
        else:
            informative = self.tr("%n files will be reset:", "", len(abortList))
            if anyConflicts:
                lines.append(self.tr("All conflicts will be cleared and all <b>staged</b> changes will be lost."))
            else:
                lines.append(self.tr("All <b>staged</b> changes will be lost."))

        yield from self.flowConfirm(title=title, text=paragraphs(lines), verb=verb, informativeText=informative,
                                    detailList=[escape(f) for f in abortList])

        self.effects |= TaskEffects.DefaultRefresh

        self.repo.reset_merge()
        self.repo.state_cleanup()

        # If cherrypicking, clear draft commit message that was set in CherrypickCommit
        if isCherryPicking or isReverting:
            self.repoModel.prefs.clearDraftCommit()
