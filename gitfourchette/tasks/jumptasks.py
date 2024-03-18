"""
Tasks that navigate to a specific area of the repository.

Unlike most other tasks, jump tasks directly manipulate the UI extensively, via RepoWidget.
"""
import logging
import os

from gitfourchette import tasks
from gitfourchette.nav import NavLocator, NavContext, NavHistory, NavFlags
from gitfourchette.porcelain import NULL_OID, DeltaStatus
from gitfourchette.qt import *
from gitfourchette.repostate import UC_FAKEID
from gitfourchette.settings import DEVDEBUG
from gitfourchette.sidebar.sidebarmodel import UC_FAKEREF
from gitfourchette.tasks.repotask import AbortTask, RepoTask, TaskEffects, RepoGoneError
from gitfourchette.toolbox import *
from gitfourchette.diffview.diffdocument import DiffDocument
from gitfourchette.diffview.specialdiff import SpecialDiffError, DiffConflict, DiffImagePair

logger = logging.getLogger(__name__)


class Jump(RepoTask):
    """
    Single entry point to navigate to any NavLocator in a repository.

    Only the Jump task may "cement" the RepoWidget's navLocator.
    """

    def canKill(self, task: 'RepoTask'):
        return isinstance(task, (Jump, RefreshRepo))

    def flow(self, locator: NavLocator):
        if not locator:
            return

        from gitfourchette.repowidget import RepoWidget
        rw: RepoWidget = self.rw
        assert isinstance(rw, RepoWidget)

        # Back up current locator
        rw.saveFilePositions()

        # Refine locator: Try to recall where we were last time we looked at this context.
        locator = rw.navHistory.refine(locator)

        # Show workdir or commit views (and update them if needed)
        if locator.context.isWorkdir():
            locator = yield from self.showWorkdir(locator)
        else:
            locator = yield from self.showCommit(locator)

        # Early out?
        if locator is None:
            return

        if locator.context == NavContext.COMMITTED:
            flv = rw.committedFiles
        elif locator.context == NavContext.STAGED:
            flv = rw.stagedFiles
        else:
            flv = rw.dirtyFiles

        # If we still don't have a path in the locator, fall back to first path in file list.
        if not locator.path:
            locator = locator.replace(path=flv.getFirstPath())
            locator = rw.navHistory.refine(locator)

        with QSignalBlockerContext(rw.dirtyFiles, rw.stagedFiles, rw.committedFiles):
            # Clear selection in other FileListViews
            for otherFlv in rw.dirtyFiles, rw.stagedFiles, rw.committedFiles:
                if otherFlv is not flv:
                    otherFlv.clearSelection()

            # Select correct row in file list
            anyFile = False
            if locator.path:
                # Fix multiple "ghost" selections in DirtyFiles/StagedFiles with JumpBackOrForward.
                if not locator.hasFlags(NavFlags.AllowMultiSelect):
                    flv.clearSelection()

                anyFile = flv.selectFile(locator.path)

            rw.stageButton.setEnabled(False)
            rw.unstageButton.setEnabled(False)
            if anyFile:
                if flv is rw.stagedFiles:
                    rw.unstageButton.setEnabled(True)
                    rw.dirtyFiles.highlightCounterpart(locator)
                elif flv is rw.dirtyFiles:
                    rw.stageButton.setEnabled(True)
                    rw.stagedFiles.highlightCounterpart(locator)

            # Set correct card in filesStack (after selecting the file to avoid flashing)
            if locator.context == NavContext.COMMITTED:
                rw.setFileStackPage("commit")
            else:
                rw.setFileStackPage("workdir")

            if not anyFile:
                flv.clearSelection()
                rw.clearDiffView()
                return

        self.setFinalLocator(locator)
        rw.diffHeader.setText(locator.asTitle())

        # Load patch in DiffView
        patch = flv.getPatchForFile(locator.path)
        patchTask: tasks.LoadPatch = yield from self.flowSubtask(tasks.LoadPatch, patch, locator)
        result = patchTask.result
        resultType = type(result)

        if resultType is DiffConflict:
            rw.setDiffStackPage("conflict")
            rw.conflictView.displayConflict(result)

        elif resultType is SpecialDiffError:
            rw.setDiffStackPage("special")
            rw.specialDiffView.displaySpecialDiffError(result)

        elif resultType is DiffDocument:
            rw.setDiffStackPage("text")
            if DEVDEBUG:
                prefix = shortHash(patch.delta.old_file.id) + ".." + shortHash(patch.delta.new_file.id)
                rw.diffHeader.setText(f"({prefix}) {rw.diffHeader.text()}")
            rw.diffView.replaceDocument(rw.repo, patch, locator, result)

        elif resultType is DiffImagePair:
            rw.setDiffStackPage("special")
            rw.specialDiffView.displayImageDiff(patch.delta, result.oldImage, result.newImage)

        else:
            rw.setDiffStackPage("special")
            rw.specialDiffView.displaySpecialDiffError(SpecialDiffError(
                self.tr("Can’t display diff of type {0}.").format(escape(str(type(result)))),
                icon=QStyle.StandardPixmap.SP_MessageBoxCritical))

    def showWorkdir(self, locator: NavLocator):
        from gitfourchette.repowidget import RepoWidget
        rw: RepoWidget = self.rw
        assert isinstance(rw, RepoWidget)

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
            rw.dirtyHeader.setText(self.tr("%n dirty:", "", nDirty))
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

        # Special case if workdir is clean
        if rw.dirtyFiles.isEmpty() and rw.stagedFiles.isEmpty():
            rw.setFileStackPage("workdir")
            rw.setDiffStackPage("special")
            rw.diffHeader.setText(self.tr("Working directory cleanWorkdir clean"))
            rw.specialDiffView.displaySpecialDiffError(SpecialDiffError(
                self.tr("The working directory is clean."),
                self.tr("There aren’t any changes to commit."),
                QStyle.StandardPixmap.SP_MessageBoxInformation))
            self.setFinalLocator(locator.replace(path=""))
            return None  # Force early out

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

    def showCommit(self, locator: NavLocator) -> NavLocator:
        """
        Jump to a commit.
        Return a refined NavLocator.
        """

        from gitfourchette.repowidget import RepoWidget
        rw: RepoWidget = self.rw
        assert isinstance(rw, RepoWidget)

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
        with QSignalBlockerContext(rw.graphView, rw.sidebar):  # Don't emit jump signals
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

            # Show message if commit is empty
            if flv.isEmpty():
                rw.setDiffStackPage("special")
                rw.specialDiffView.displaySpecialDiffError(SpecialDiffError(self.tr("Empty commit.")))

            # Set header text
            rw.committedHeader.setText(self.tr("%n changes in {0}:", "", numChanges
                                               ).format(shortHash(locator.commit)))
            rw.committedHeader.setToolTip("<p>" + escape(summary).replace("\n", "<br>"))

        # Special case if there are no changes
        if flv.isEmpty():
            rw.setFileStackPage("commit")
            rw.setDiffStackPage("special")
            rw.diffHeader.setText(self.tr("Empty commit"))
            rw.specialDiffView.displaySpecialDiffError(SpecialDiffError(
                self.tr("This commit is empty."),
                self.tr("Commit {0} doesn’t affect any files.").format(hquo(shortHash(locator.commit))),
                QStyle.StandardPixmap.SP_MessageBoxInformation))
            self.setFinalLocator(locator.replace(path=""))
            return None  # Force early out

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

    def setFinalLocator(self, locator: NavLocator):
        from gitfourchette.repowidget import RepoWidget
        rw: RepoWidget = self.rw
        assert isinstance(rw, RepoWidget)

        # Clear Force flag before saving the locator
        # (otherwise switching back and forth into the app may reload a commit)
        locator = locator.withoutFlags(NavFlags.Force)

        rw.navLocator = locator
        rw.navHistory.push(locator)
        logger.debug(f"Jump to: {locator}")


class JumpBackOrForward(tasks.RepoTask):
    """
    Navigate back or forward in the RepoWidget's NavHistory.
    """

    def flow(self, delta: int):
        from gitfourchette.repowidget import RepoWidget
        rw: RepoWidget = self.rw
        assert isinstance(rw, RepoWidget)

        start = rw.saveFilePositions()

        # Isolate history as we modify it so Jump task doesn't mess it up
        history = rw.navHistory
        rw.navHistory = NavHistory()

        while history.canGoDelta(delta):
            # Move back or forward in the history
            locator = history.navigateDelta(delta)

            # Keep going if same file comes up several times in a row
            if locator.isSimilarEnoughTo(start):
                continue

            # Jump
            yield from self.flowSubtask(Jump, locator)

            # The jump was successful if the RepoWidget's locator
            # comes out similar enough to the one from the history.
            if rw.navLocator.isSimilarEnoughTo(locator):
                break

            # This point in history is stale, nuke it and keep going
            history.popCurrent()

        # Restore history
        history.push(rw.navLocator)
        rw.navHistory = history


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
        from gitfourchette.repowidget import RepoWidget
        rw: RepoWidget = self.rw
        assert isinstance(rw, RepoWidget)
        assert onAppThread()

        if effectFlags == TaskEffects.Nothing:
            return

        # Early out if repo has gone missing
        if not os.path.isdir(self.repo.path):
            raise RepoGoneError(self.repo.path)

        rw.state.workdirStale |= bool(effectFlags & TaskEffects.Workdir)

        oldActiveCommit = rw.state.activeCommitOid
        initialLocator = rw.navLocator
        initialGraphScroll = rw.graphView.verticalScrollBar().value()

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
            if initialLocator.commit in rw.state.graph.commitRows:
                jumpTo = initialLocator
            else:
                # Old commit is gone - jump to HEAD
                jumpTo = NavLocator.inCommit(rw.state.activeCommitOid)

        yield from self.flowSubtask(Jump, jumpTo)

        # Refresh window title and status bar warning bubbles.
        # Do this last because it requires the index to be fresh (updated by the Jump subtask)
        rw.refreshWindowChrome()
