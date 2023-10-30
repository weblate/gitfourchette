"""
Tasks that navigate to a specific area of the repository.

Unlike most other tasks, jump tasks directly manipulate the UI extensively, via RepoWidget.
"""
from gitfourchette import log, tasks
from gitfourchette.nav import NavLocator, NavContext, NavHistory, NavFlags
from gitfourchette.qt import *
from gitfourchette.tasks import RepoTask, TaskEffects, RepoGoneError
from gitfourchette.toolbox import *
from gitfourchette.diffview.diffdocument import DiffDocument
from gitfourchette.diffview.specialdiff import SpecialDiffError, DiffConflict, DiffImagePair

TAG = "Jump"


class Jump(RepoTask):
    """
    Single entry point to navigate to any NavLocator in a repository.

    Only the Jump task may "cement" the RepoWidget's navLocator.
    """

    def name(self):
        return self.tr("Navigate in repo")

    @property
    def rw(self):
        from gitfourchette.repowidget import RepoWidget
        rw: RepoWidget = self.parentWidget()
        assert isinstance(rw, RepoWidget)
        return rw

    def canKill(self, task: 'RepoTask'):
        return isinstance(task, (Jump, RefreshRepo))

    def flow(self, locator: NavLocator):
        if not locator:
            return

        rw = self.rw
        log.info(TAG, locator)

        # Back up current locator
        rw.saveFilePositions()

        # Refine locator: Try to recall where we were last time we looked at this context.
        locator = rw.navHistory.refine(locator)
        log.info(TAG, "locator refined to:", locator)

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
                anyFile = flv.selectFile(locator.path)

            # Set correct card in filesStack (after selecting the file to avoid flashing)
            if locator.context == NavContext.COMMITTED:
                rw.filesStack.setCurrentWidget(rw.committedFilesContainer)
            else:
                rw.filesStack.setCurrentWidget(rw.stageSplitter)

            if not anyFile:
                flv.clearSelection()
                rw.clearDiffView()
                return

        self.setFinalLocator(locator)
        rw.diffHeader.setText(locator.asTitle())

        # Load patch in DiffView
        patch = flv.getPatchForFile(locator.path)
        patchTask: tasks.LoadPatch = yield from self._flowSubtask(tasks.LoadPatch, patch, locator)
        result = patchTask.result

        if type(result) == DiffConflict:
            rw.diffStack.setCurrentWidget(rw.conflictView)
            rw.conflictView.displayConflict(result)
        elif type(result) == SpecialDiffError:
            rw.diffStack.setCurrentWidget(rw.specialDiffView)
            rw.specialDiffView.displaySpecialDiffError(result)
        elif type(result) == DiffDocument:
            rw.diffStack.setCurrentWidget(rw.diffView)
            if DEVDEBUG:
                prefix = shortHash(patch.delta.old_file.id) + ".." + shortHash(patch.delta.new_file.id)
                rw.diffHeader.setText(f"({prefix}) {rw.diffHeader.text()}")
            rw.diffView.replaceDocument(rw.repo, patch, locator, result)
        elif type(result) == DiffImagePair:
            rw.diffStack.setCurrentWidget(rw.specialDiffView)
            rw.specialDiffView.displayImageDiff(patch.delta, result.oldImage, result.newImage)
        else:
            rw.diffStack.setCurrentWidget(rw.specialDiffView)
            rw.specialDiffView.displaySpecialDiffError(SpecialDiffError(
                self.tr("Can’t display diff of type {0}.").format(escape(str(type(result)))),
                icon=QStyle.StandardPixmap.SP_MessageBoxCritical))

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
            rw.sidebar.selectAnyRef("UNCOMMITTED_CHANGES")

        # Stale workdir model - force load workdir
        if (previousLocator.context == NavContext.EMPTY
                or locator.hasFlags(NavFlags.ForceRefreshWorkdir)
                or rw.state.workdirStale):
            # Don't clear stale flag until AFTER we're done reloading the workdir
            # so that it stays stale if this task gets interrupted.
            rw.state.workdirStale = True

            # Load workdir (async)
            workdirTask: tasks.LoadWorkdir = yield from self._flowSubtask(
                tasks.LoadWorkdir, allowWriteIndex=locator.hasFlags(NavFlags.AllowWriteIndex))

            # Fill FileListViews
            with QSignalBlockerContext(rw.dirtyFiles, rw.stagedFiles):  # Don't emit jump signals
                rw.dirtyFiles.setContents([workdirTask.dirtyDiff])
                rw.stagedFiles.setContents([workdirTask.stageDiff])

            nDirty = rw.dirtyFiles.model().rowCount()
            nStaged = rw.stagedFiles.model().rowCount()
            rw.dirtyHeader.setText(self.tr("%n dirty file(s):", "", nDirty))
            rw.stagedHeader.setText(self.tr("%n file(s) staged for commit:", "", nStaged))

            newNumChanges = nDirty + nStaged
            numChangesDifferent = rw.state.numChanges != newNumChanges
            rw.state.numChanges = newNumChanges

            rw.state.workdirStale = False

            # Show number of staged changes in sidebar
            if numChangesDifferent:
                rw.sidebar.repaint()

        # If jumping to generic workdir context, find a concrete context
        if locator.context == NavContext.WORKDIR:
            if rw.dirtyFiles.isEmpty() and not rw.stagedFiles.isEmpty():
                locator = locator.replace(context=NavContext.STAGED)
            else:
                locator = locator.replace(context=NavContext.UNSTAGED)
            locator = rw.navHistory.refine(locator)

        # Special case if workdir is clean
        if rw.dirtyFiles.isEmpty() and rw.stagedFiles.isEmpty():
            rw.filesStack.setCurrentWidget(rw.stageSplitter)
            rw.diffStack.setCurrentWidget(rw.specialDiffView)
            rw.diffHeader.setText(self.tr("Working directory clean"))
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

    def showCommit(self, locator: NavLocator):
        rw = self.rw

        # Select row in commit log
        with QSignalBlockerContext(rw.graphView, rw.sidebar):  # Don't emit jump signals
            silent = locator.hasFlags(NavFlags.IgnoreInvalidLocation)
            commitFound = rw.graphView.selectCommit(locator.commit, silent=silent)

        # Commit is gone (hidden or not loaded yet)
        if not commitFound:
            yield from self._flowAbort()

        # Attempt to select matching ref in sidebar
        with (
            QSignalBlockerContext(rw.sidebar),  # Don't emit jump signals
            QScrollBackupContext(rw.sidebar),  # Stabilize scroll bar value
        ):
            refCandidates = rw.state.reverseRefCache.get(locator.commit, [])
            rw.sidebar.selectAnyRef(*refCandidates)

        flv = rw.committedFiles

        if flv.commitOid == locator.commit:
            # No need to reload the same commit
            pass

        else:
            # Load commit (async)
            subtask: tasks.LoadCommit = yield from self._flowSubtask(tasks.LoadCommit, locator.commit)

            # Get data from subtask
            diffs = subtask.diffs
            summary = subtask.message.strip()

            # Fill committed file list
            with QSignalBlockerContext(flv):  # Don't emit jump signals
                flv.clear()
                flv.setCommit(locator.commit)
                flv.setContents(diffs)
                numChanges = flv.model().rowCount()

            # Show message if commit is empty
            if flv.isEmpty():
                rw.diffStack.setCurrentWidget(rw.specialDiffView)
                rw.specialDiffView.displaySpecialDiffError(SpecialDiffError(self.tr("Empty commit.")))

            # Set header text
            rw.committedHeader.setText(self.tr("%n change(s) in {0}:", "", numChanges
                                               ).format(shortHash(locator.commit)))
            rw.committedHeader.setToolTip("<p>" + escape(summary).replace("\n", "<br>"))

        # Special case if there are no changes
        if flv.isEmpty():
            rw.filesStack.setCurrentWidget(rw.committedFilesContainer)
            rw.diffStack.setCurrentWidget(rw.specialDiffView)
            rw.diffHeader.setText(self.tr("Empty commit"))
            rw.specialDiffView.displaySpecialDiffError(SpecialDiffError(
                self.tr("This commit is empty."),
                self.tr("Commit “{0}” doesn’t affect any files.").format(shortHash(locator.commit)),
                QStyle.StandardPixmap.SP_MessageBoxInformation))
            self.setFinalLocator(locator.replace(path=""))
            return None  # Force early out

        return locator

    def setFinalLocator(self, locator: NavLocator):
        rw = self.rw
        rw.navLocator = locator
        rw.navHistory.push(locator)
        log.info(TAG, "locator set to:", locator)


class JumpBackOrForward(tasks.RepoTask):
    """
    Navigate back or forward in the RepoWidget's NavHistory.
    """

    def flow(self, delta: int):
        from gitfourchette.repowidget import RepoWidget

        rw: RepoWidget = self.parentWidget()
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
            yield from self._flowSubtask(Jump, locator)

            # The jump was successful if the RepoWidget's locator
            # comes out similar enough to the one from the history.
            if rw.navLocator.isSimilarEnoughTo(locator):
                break

            # This point in history is stale, nuke it and keep going
            history.popCurrent()

        # Restore history
        history.push(rw.navLocator)
        rw.navHistory = history


class RefreshRepo(tasks.RepoTask):
    def name(self):
        return self.tr("Refresh repo")

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

        rw: RepoWidget = self.parentWidget()
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
            anyRefsChanged = rw.state.refreshRefCache()

            # Load commits from changed refs only
            if anyRefsChanged:
                assert onAppThread()  # loadTaintedCommitsOnly is not thread safe for now
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
                log.info(TAG, "Refresh: No refs changed.")

        # Schedule a repaint of the entire GraphView if the refs changed
        if effectFlags & (TaskEffects.Head | TaskEffects.Refs):
            rw.graphView.viewport().update()

        # Refresh sidebar
        with QSignalBlockerContext(rw.sidebar):
            rw.sidebar.refresh(rw.state)

        rw.refreshWindowTitle()

        # Now jump to where we should be after the refresh
        assert rw.navLocator == initialLocator, "locator has changed"

        jumpTo = jumpTo or initialLocator

        if rw.isWorkdirShown or effectFlags & TaskEffects.ShowWorkdir:
            # Refresh workdir view on separate thread AFTER all the processing above
            if not jumpTo.context.isWorkdir():
                jumpTo = NavLocator(NavContext.WORKDIR)

            if effectFlags & TaskEffects.Workdir:
                newFlags = jumpTo.flags | NavFlags.ForceRefreshWorkdir | NavFlags.AllowWriteIndex
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

        yield from self._flowSubtask(Jump, jumpTo)
