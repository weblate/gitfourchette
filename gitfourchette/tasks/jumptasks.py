"""
Tasks that navigate to a specific area of the repository.

Unlike most other tasks, jump tasks directly manipulate the UI extensively, via RepoWidget.
"""
import dataclasses
import logging
import os

from gitfourchette import tasks, colors, settings
from gitfourchette.diffview.diffdocument import DiffDocument
from gitfourchette.diffview.specialdiff import SpecialDiffError, DiffConflict, DiffImagePair
from gitfourchette.graphview.commitlogmodel import SpecialRow
from gitfourchette.nav import NavLocator, NavContext, NavFlags
from gitfourchette.porcelain import NULL_OID, DeltaStatus, Patch
from gitfourchette.qt import *
from gitfourchette.repostate import UC_FAKEID
from gitfourchette.settings import DEVDEBUG
from gitfourchette.sidebar.sidebarmodel import UC_FAKEREF
from gitfourchette.tasks.repotask import AbortTask, RepoTask, TaskEffects, RepoGoneError
from gitfourchette.toolbox import *

logger = logging.getLogger(__name__)


class Jump(RepoTask):
    """
    Single entry point to navigate to any NavLocator in a repository.

    Only the Jump task may "cement" the RepoWidget's navLocator.
    """

    @dataclasses.dataclass
    class Result(Exception):
        locator: NavLocator
        header: str
        document: DiffDocument | DiffConflict | DiffImagePair | SpecialDiffError | None
        patch: Patch = None

    def canKill(self, task: RepoTask):
        return isinstance(task, (Jump, RefreshRepo))

    def flow(self, locator: NavLocator):
        if not locator:
            return

        rw = self.rw

        # Back up current locator
        if not rw.navHistory.isWriteLocked():
            rw.saveFilePositions()

        # Refine locator: Try to recall where we were last time we looked at this context.
        locator = rw.navHistory.refine(locator)

        try:
            # Show workdir or commit views (and update them if needed)
            if locator.context == NavContext.SPECIAL:
                self.showSpecial(locator)  # always raises Jump.Result
            elif locator.context.isWorkdir():
                locator = yield from self.showWorkdir(locator)
            else:
                locator = yield from self.showCommit(locator)

            # Select correct file in FileList
            locator = self.selectCorrectFile(locator)

            # Load patch in DiffView
            patch = rw.fileListByContext(locator.context).getPatchForFile(locator.path)
            patchTask: tasks.LoadPatch = yield from self.flowSubtask(tasks.LoadPatch, patch, locator)
            result = Jump.Result(locator, patchTask.header, patchTask.result, patch)
        except Jump.Result as r:
            # The block above may be stopped early by raising Jump.Result.
            result = r

        locator = result.locator
        self.saveFinalLocator(locator)

        # Set correct card in fileStack (may have been done by selectCorrectFile
        # above, but do it again in case a Result was raised early)
        self.rw.setFileStackPageByContext(locator.context)

        self.displayResult(result)

    def showWorkdir(self, locator: NavLocator):
        rw = self.rw
        previousLocator = rw.navLocator

        # Save selected row number for the end of the function
        previousRowStaged = rw.stagedFiles.earliestSelectedRow()
        previousRowDirty = rw.dirtyFiles.earliestSelectedRow()

        with (
            QSignalBlockerContext(rw.graphView, rw.sidebar),  # Don't emit jump signals
            QScrollBackupContext(rw.sidebar),  # Stabilize scroll bar value
        ):
            rw.graphView.selectUncommittedChanges()
            rw.sidebar.selectAnyRef(UC_FAKEREF)

        # Reset diff banner
        rw.diffBanner.setVisible(False)

        # Stale workdir model - force load workdir
        if (previousLocator.context == NavContext.EMPTY
                or locator.hasFlags(NavFlags.Force)
                or rw.state.workdirStale):
            # Don't clear stale flag until AFTER we're done reloading the workdir
            # so that it stays stale if this task gets interrupted.
            rw.state.workdirStale = True

            # Load workdir (async)
            workdirTask: tasks.LoadWorkdir = yield from self.flowSubtask(
                tasks.LoadWorkdir, allowWriteIndex=locator.hasFlags(NavFlags.AllowWriteIndex))

            # Fill FileListViews
            with QSignalBlockerContext(rw.dirtyFiles, rw.stagedFiles):  # Don't emit jump signals
                rw.dirtyFiles.setContents([workdirTask.dirtyDiff], False)
                rw.stagedFiles.setContents([workdirTask.stageDiff], False)

            nDirty = rw.dirtyFiles.model().rowCount()
            nStaged = rw.stagedFiles.model().rowCount()
            rw.dirtyHeader.setText(self.tr("%n unstaged:", "", nDirty))
            rw.stagedHeader.setText(self.tr("%n staged:", "", nStaged))

            newNumChanges = nDirty + nStaged
            numChangesDifferent = rw.state.numUncommittedChanges != newNumChanges
            rw.state.numUncommittedChanges = newNumChanges

            rw.state.workdirStale = False

            # Show number of staged changes in sidebar and graph
            if numChangesDifferent:
                rw.sidebar.repaint()
                rw.graphView.repaintCommit(UC_FAKEID)

        # If jumping to generic workdir context, find a concrete context
        if locator.context == NavContext.WORKDIR:
            if rw.dirtyFiles.isEmpty() and not rw.stagedFiles.isEmpty():
                locator = locator.replace(context=NavContext.STAGED)
            else:
                locator = locator.replace(context=NavContext.UNSTAGED)
            locator = rw.navHistory.refine(locator)

        # Early out if workdir is clean
        if rw.dirtyFiles.isEmpty() and rw.stagedFiles.isEmpty():
            locator = locator.replace(path="")
            header = self.tr("Working directory cleanWorkdir clean")
            sde = SpecialDiffError(
                self.tr("The working directory is clean."),
                self.tr("There aren’t any changes to commit."))
            raise Jump.Result(locator, header, sde)

        # (Un)Staging a file makes it vanish from its file list.
        # But we don't want the selection to go blank in this case.
        # Restore selected row (by row number) in the file list so the user
        # can keep hitting RETURN/DELETE to stage/unstage a series of files.
        isStaged = locator.context == NavContext.STAGED
        flModel = (rw.stagedFiles if isStaged else rw.dirtyFiles).flModel
        flPrevRow = previousRowStaged if isStaged else previousRowDirty
        if locator.path and not flModel.hasFile(locator.path) and flPrevRow >= 0:
            path = flModel.getFileAtRow(min(flPrevRow, flModel.rowCount()-1))
            locator = locator.replace(path=path)
            locator = rw.navHistory.refine(locator)

        return locator

    def showSpecial(self, locator: NavLocator):
        rw = self.rw
        locale = QLocale()

        with QSignalBlockerContext(rw.sidebar, rw.committedFiles):
            rw.sidebar.clearSelection()
            rw.committedFiles.clear()
            rw.committedHeader.setText(" ")
            rw.diffBanner.hide()

        if locator.path == str(SpecialRow.EndOfShallowHistory):
            sde = SpecialDiffError(
                self.tr("Shallow clone – End of available history.").format(locale.toString(self.rw.state.numRealCommits)),
                self.tr("More commits may be available in a full clone."))
            raise Jump.Result(locator, self.tr("Shallow clone – End of commit history"), sde)

        elif locator.path == str(SpecialRow.TruncatedHistory):
            from gitfourchette import settings
            prefThreshold = settings.prefs.graph_maxCommits
            nextThreshold = rw.state.nextTruncationThreshold
            expandSome = makeInternalLink("expandlog")
            expandAll = makeInternalLink("expandlog", n=str(0))
            changePref = makeInternalLink("prefs", "graph_maxCommits")
            options = [
                linkify(self.tr("Load up to {0} commits").format(locale.toString(nextThreshold)), expandSome),
                linkify(self.tr("[Load full commit history] (this may take a moment)"), expandAll),
                linkify(self.tr("[Change threshold setting] (currently {0} commits)"), changePref).format(locale.toString(prefThreshold)),
            ]
            sde = SpecialDiffError(
                self.tr("History truncated to {0} commits.").format(locale.toString(self.rw.state.numRealCommits)),
                self.tr("More commits may be available."),
                longform=toRoomyUL(options))
            raise Jump.Result(locator, self.tr("History truncated"), sde)

        else:
            raise Jump.Result(locator, "", SpecialDiffError(f"Unsupported special locator: {locator}"))

    def showCommit(self, locator: NavLocator) -> NavLocator:
        """
        Jump to a commit.
        Return a refined NavLocator.
        """

        rw = self.rw
        assert locator.context == NavContext.COMMITTED

        # If it's a ref, look it up
        if locator.ref:
            assert locator.commit == NULL_OID
            try:
                oid = rw.state.refCache[locator.ref]
                locator = locator.replace(commit=oid, ref="")
            except KeyError:
                raise AbortTask(self.tr("Unknown reference {0}.").format(tquo(locator.ref)))

        assert locator.commit
        assert not locator.ref

        warnings = []

        # Select row in commit log
        from gitfourchette.graphview.graphview import GraphView
        with QSignalBlockerContext(rw.graphView):  # Don't emit jump signals
            try:
                rw.graphView.selectCommit(locator.commit, silent=False)
            except GraphView.SelectCommitError as e:
                # Commit is hidden or not loaded
                rw.graphView.clearSelection()
                warnings.append(str(e))

        # Attempt to select matching ref in sidebar
        with (
            QSignalBlockerContext(rw.sidebar),  # Don't emit jump signals
            QScrollBackupContext(rw.sidebar),  # Stabilize scroll bar value
        ):
            refCandidates = rw.state.reverseRefCache.get(locator.commit, [])
            rw.sidebar.selectAnyRef(*refCandidates)

        flv = rw.committedFiles
        rw.diffBanner.setVisible(False)

        if locator.commit == flv.commitOid and not locator.hasFlags(NavFlags.Force):
            # No need to reload the same commit
            # (if this flv was dormant and is sent back to the foreground).
            pass

        else:
            # Loading a different commit
            rw.diffBanner.lastWarningWasDismissed = False

            # Load commit (async)
            subtask = yield from self.flowSubtask(tasks.LoadCommit, locator)
            assert isinstance(subtask, tasks.LoadCommit)

            # Get data from subtask
            diffs = subtask.diffs
            summary = subtask.message.strip()

            # Fill committed file list
            with QSignalBlockerContext(flv):  # Don't emit jump signals
                flv.clear()
                flv.setCommit(locator.commit)
                flv.setContents(diffs, subtask.skippedRenameDetection)
                numChanges = flv.model().rowCount()

            # Set header text
            rw.committedHeader.setText(self.tr("%n changes in {0}:", "", numChanges
                                               ).format(shortHash(locator.commit)))
            rw.committedHeader.setToolTip("<p>" + escape(summary).replace("\n", "<br>"))

        # Early out if the commit is empty
        if flv.isEmpty():
            locator = locator.replace(path="")
            header = self.tr("Empty commit")
            sde = SpecialDiffError(
                self.tr("This commit is empty."),
                self.tr("Commit {0} doesn’t affect any files.").format(hquo(shortHash(locator.commit))))
            raise Jump.Result(locator, header, sde)

        # Warning banner
        if not rw.diffBanner.lastWarningWasDismissed:
            buttonLabel = ""
            buttonCallback = None

            if flv.skippedRenameDetection:
                warnings.append(self.tr("Rename detection was skipped to load this large commit faster."))
                buttonLabel = self.tr("Detect Renames")
                buttonCallback = lambda: Jump.invoke(rw, locator.withExtraFlags(NavFlags.AllowLargeCommits | NavFlags.Force))
            elif locator.hasFlags(NavFlags.AllowLargeCommits | NavFlags.Force):
                n = sum(sum(1 if delta.status == DeltaStatus.RENAMED else 0 for delta in diff.deltas) for diff in diffs)
                warnings.append(self.tr("%n renames detected.", "", n))

            if warnings:
                warningText = "<br>".join(warnings)
                rw.diffBanner.setVisible(True)
                rw.diffBanner.popUp("", warningText, canDismiss=True, withIcon=True,
                                    buttonLabel=buttonLabel, buttonCallback=buttonCallback)

        return locator

    def selectCorrectFile(self, locator: NavLocator):
        rw = self.rw
        flv = rw.fileListByContext(locator.context)

        # If we still don't have a path in the locator, fall back to first path in file list.
        if not locator.path:
            locator = locator.replace(path=flv.firstPath())
            locator = rw.navHistory.refine(locator)

        with QSignalBlockerContext(rw.dirtyFiles, rw.stagedFiles, rw.committedFiles):
            # Select correct row in file list
            anyFile = False
            if locator.path:
                # Fix multiple "ghost" selections in DirtyFiles/StagedFiles with JumpBackOrForward.
                if not locator.hasFlags(NavFlags.AllowMultiSelect):
                    flv.clearSelection()
                # Select the file, if possible
                anyFile = flv.selectFile(locator.path)

            # Special treatment for workdir
            if locator.context.isWorkdir():
                # Clear selection in other workdir FileList
                otherFlv = rw.stagedFiles if locator.context != NavContext.STAGED else rw.dirtyFiles
                otherFlv.clearSelection()

                if not anyFile:
                    rw.stageButton.setEnabled(False)
                    rw.unstageButton.setEnabled(False)
                elif locator.context == NavContext.STAGED:
                    rw.unstageButton.setEnabled(True)
                    rw.stageButton.setEnabled(False)
                    rw.dirtyFiles.highlightCounterpart(locator)
                else:
                    rw.unstageButton.setEnabled(False)
                    rw.stageButton.setEnabled(True)
                    rw.stagedFiles.highlightCounterpart(locator)

            # Early out if selection remains blank
            if not anyFile:
                flv.clearSelection()
                locator = locator.replace(path="")
                raise Jump.Result(locator, "", None)

        # Set correct card in fileStack (after selecting the file to avoid flashing)
        self.rw.setFileStackPageByContext(locator.context)

        return locator

    def saveFinalLocator(self, locator: NavLocator):
        # Clear Force flag before saving the locator
        # (otherwise switching back and forth into the app may reload a commit)
        locator = locator.withoutFlags(NavFlags.Force)

        self.rw.navLocator = locator

        if not self.rw.navHistory.isWriteLocked():
            self.rw.navHistory.push(locator)
            self.rw.historyChanged.emit()

    def displayResult(self, result: Result):
        rw = self.rw

        # Set header
        rw.diffHeader.setText(result.header)

        document = result.document
        documentType = type(document)

        if document is None:
            rw.clearDiffView()

        elif documentType is DiffDocument:
            rw.setDiffStackPage("text")
            rw.diffView.replaceDocument(rw.repo, result.patch, result.locator, document)

        elif documentType is DiffConflict:
            rw.setDiffStackPage("conflict")
            rw.conflictView.displayConflict(document)

        elif documentType is SpecialDiffError:
            rw.setDiffStackPage("special")
            rw.specialDiffView.displaySpecialDiffError(document)

        elif documentType is DiffImagePair:
            rw.setDiffStackPage("special")
            rw.specialDiffView.displayImageDiff(result.patch.delta, document.oldImage, document.newImage)

        else:
            rw.setDiffStackPage("special")
            rw.specialDiffView.displaySpecialDiffError(SpecialDiffError(
                escape(f"Can't display {documentType}."),
                icon="SP_MessageBoxCritical"))


class JumpBackOrForward(tasks.RepoTask):
    """
    Navigate back or forward in the RepoWidget's NavHistory.
    """

    def flow(self, delta: int):
        rw = self.rw

        start = rw.saveFilePositions()
        history = rw.navHistory

        while history.canGoDelta(delta):
            # Move back or forward in the history
            locator = history.navigateDelta(delta)

            # Keep going if same file comes up several times in a row
            if locator.isSimilarEnoughTo(start):
                continue

            # Jump
            # (lock history because we want full control over it)
            with history.writeLock:
                yield from self.flowSubtask(Jump, locator)

            # The jump was successful if the RepoWidget's locator
            # comes out similar enough to the one from the history.
            if rw.navLocator.isSimilarEnoughTo(locator):
                break

            # This point in history is stale, nuke it and keep going
            history.popCurrent()

        # Finalize history
        history.push(rw.navLocator)
        rw.historyChanged.emit()


class JumpBack(JumpBackOrForward):
    def flow(self):
        yield from JumpBackOrForward.flow(self, -1)


class JumpForward(JumpBackOrForward):
    def flow(self):
        yield from JumpBackOrForward.flow(self, 1)


class RefreshRepo(tasks.RepoTask):
    @staticmethod
    def canKill_static(task: RepoTask):
        return task is None or isinstance(task, (Jump, RefreshRepo))

    def canKill(self, task: RepoTask):
        return RefreshRepo.canKill_static(task)

    def effects(self) -> TaskEffects:
        # Stop refresh chain here - this task is responsible for other post-task refreshes
        return TaskEffects.Nothing

    def flow(self, effectFlags: TaskEffects = TaskEffects.DefaultRefresh, jumpTo: NavLocator = None):
        rw = self.rw
        assert onAppThread()

        if effectFlags == TaskEffects.Nothing:
            return

        # Early out if repo has gone missing
        if not os.path.isdir(self.repo.path):
            raise RepoGoneError(self.repo.path)

        rw.state.workdirStale |= bool(effectFlags & TaskEffects.Workdir)

        initialLocator = rw.navLocator
        initialGraphScroll = rw.graphView.verticalScrollBar().value()

        try:
            previousFileList = rw.fileListByContext(initialLocator.context)
            previousFileList.backUpSelection()
        except ValueError:
            previousFileList = None

        if effectFlags & (TaskEffects.Refs | TaskEffects.Remotes | TaskEffects.Head):
            # Refresh ref cache
            oldRefCache = rw.state.refCache
            needGraphRefresh = rw.state.refreshRefCache()
            needGraphRefresh |= rw.state.refreshMergeheadsCache()

            # Load commits from changed refs only
            if needGraphRefresh:
                # Make sure we're on the UI thread.
                # We don't want GraphView to try to read an incomplete state while repainting.
                assert onAppThread()

                nRemovedRows, nAddedRows = rw.state.loadChangedRefs(oldRefCache)

                # Refresh top of graphview
                with QSignalBlockerContext(rw.graphView):
                    # Hidden commits may have changed in RepoState.loadTaintedCommitsOnly!
                    # If new commits are part of a hidden branch, we've got to invalidate the CommitFilter.
                    rw.graphView.setHiddenCommits(rw.state.hiddenCommits)
                    if nRemovedRows >= 0:
                        rw.graphView.refreshTopOfCommitSequence(nRemovedRows, nAddedRows, rw.state.commitSequence)
                    else:
                        rw.graphView.setCommitSequence(rw.state.commitSequence)
            else:
                logger.debug("Don't need to refresh the graph.")

        # Schedule a repaint of the entire GraphView if the refs changed
        if effectFlags & (TaskEffects.Head | TaskEffects.Refs):
            rw.graphView.viewport().update()

        # Refresh sidebar
        with QSignalBlockerContext(rw.sidebar):
            rw.sidebar.refresh(rw.state)

        # Now jump to where we should be after the refresh
        assert rw.navLocator == initialLocator, "locator has changed"

        jumpTo = jumpTo or initialLocator

        if rw.isWorkdirShown or effectFlags & TaskEffects.ShowWorkdir:
            # Refresh workdir view on separate thread AFTER all the processing above
            if not jumpTo.context.isWorkdir():
                jumpTo = NavLocator(NavContext.WORKDIR)

            if effectFlags & TaskEffects.Workdir:
                newFlags = jumpTo.flags | NavFlags.Force | NavFlags.AllowWriteIndex
                jumpTo = jumpTo.replace(flags=newFlags)

        elif initialLocator and initialLocator.context == NavContext.COMMITTED:
            # After inserting/deleting rows in the commit log model,
            # the selected row may jump around. Try to restore the initial
            # locator to ensure the previously selected commit stays selected.
            rw.graphView.verticalScrollBar().setValue(initialGraphScroll)
            if jumpTo == initialLocator and jumpTo.commit not in rw.state.graph.commitRows:
                # Old commit is gone - jump to HEAD
                jumpTo = NavLocator.inCommit(rw.state.activeCommitOid)

        yield from self.flowSubtask(Jump, jumpTo)

        # Try to restore path selection
        if previousFileList is None:
            pass
        elif initialLocator.isSimilarEnoughTo(jumpTo):
            previousFileList.restoreSelectionBackup()
        else:
            previousFileList.clearSelectionBackup()

        # Refresh window title and status bar warning bubbles.
        # Do this last because it requires the index to be fresh (updated by the Jump subtask)
        rw.refreshWindowChrome()
