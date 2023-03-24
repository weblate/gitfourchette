"""
Tasks that navigate to a specific area of the repository.

Unlike most other tasks, jump tasks directly manipulate the UI extensively, via RepoWidget.
"""

from gitfourchette import log, tasks
from gitfourchette.nav import NavLocator, NavContext
from gitfourchette.qt import *
from gitfourchette.tasks import RepoTask
from gitfourchette.util import QSignalBlockerContext, shortHash
from gitfourchette.widgets.diffmodel import DiffConflict, DiffModelError, DiffModel, DiffImagePair
from html import escape

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
        from gitfourchette.widgets.repowidget import RepoWidget
        rw: RepoWidget = self.parentWidget()
        assert isinstance(rw, RepoWidget)
        return rw

    def canKill(self, task: 'RepoTask'):
        return isinstance(task, Jump)

    def flow(self, locator: NavLocator, backup=True, warnIfMissing=False):
        if not locator:
            return

        rw = self.rw
        log.info(TAG, locator)

        if backup:
            rw.saveFilePositions()

        # Refine locator: Try to recall where we were last time we looked at this context.
        locator = rw.navHistory.refine(locator)
        log.info(TAG, "locator refined to:", locator)

        # As we do this, prevent emitting other "jump" signals
        if locator.context.isWorkdir():
            locator = yield from self.loadWorkdir(locator)
            flv = rw.stagedFiles if locator.context == NavContext.STAGED else rw.dirtyFiles
        else:
            locator = yield from self.loadCommit(locator, warnIfMissing)
            flv = rw.committedFiles

        # If we still don't have a path in the locator, fall back to first path in file list.
        # TODO: do we still need earliestSelectedRow/latestSelectedRow in workdir view?
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
        elif type(result) == DiffModelError:
            rw.diffStack.setCurrentWidget(rw.richDiffView)
            rw.richDiffView.displayDiffModelError(result)
        elif type(result) == DiffModel:
            rw.diffStack.setCurrentWidget(rw.diffView)
            rw.diffView.replaceDocument(rw.repo, patch, locator, result)
            rw.restoreDiffPosition(locator)  # restore position after we've replaced the document
        elif type(result) == DiffImagePair:
            rw.diffStack.setCurrentWidget(rw.richDiffView)
            rw.richDiffView.displayImageDiff(patch.delta, result.oldImage, result.newImage)
        else:
            rw.diffStack.setCurrentWidget(rw.richDiffView)
            rw.richDiffView.displayDiffModelError(DiffModelError(
                self.tr("Can’t display diff of type {0}.").format(escape(str(type(result)))),
                icon=QStyle.StandardPixmap.SP_MessageBoxCritical))

    def loadWorkdir(self, locator: NavLocator):
        rw = self.rw
        previousLocator = rw.navLocator

        with QSignalBlockerContext(rw.graphView, rw.sidebar):
            rw.graphView.selectUncommittedChanges()
            rw.sidebar.selectAnyRef("UNCOMMITTED_CHANGES")

        # Stale workdir model - force load workdir
        # TODO: add option to force reload even if the previouslocator's context isn't stale (e.g. when hitting F5)
        if previousLocator.context == NavContext.EMPTY:
            # Load workdir (async)
            workdirTask: tasks.LoadWorkdir = yield from self._flowSubtask(tasks.LoadWorkdir, False)

            # Fill FileListViews
            with QSignalBlockerContext(rw.dirtyFiles, rw.stagedFiles):
                rw.dirtyFiles.setContents([workdirTask.dirtyDiff])
                rw.stagedFiles.setContents([workdirTask.stageDiff])

            nDirty = rw.dirtyFiles.model().rowCount()
            nStaged = rw.stagedFiles.model().rowCount()
            rw.dirtyHeader.setText(self.tr("%n dirty file(s):", "", nDirty))
            rw.stagedHeader.setText(self.tr("%n file(s) staged for commit:", "", nStaged))

        # If jumping to generic workdir context, find a concrete context
        if locator.context == NavContext.WORKDIR:
            if rw.dirtyFiles.isEmpty() and not rw.stagedFiles.isEmpty():
                locator = locator.replace(context=NavContext.STAGED)
            else:
                locator = locator.replace(context=NavContext.UNSTAGED)

        # Special case if workdir is clean
        if rw.dirtyFiles.isEmpty() and rw.stagedFiles.isEmpty():
            rw.filesStack.setCurrentWidget(rw.stageSplitter)
            rw.diffStack.setCurrentWidget(rw.richDiffView)
            rw.diffHeader.setText(self.tr("Working directory clean"))
            rw.richDiffView.displayDiffModelError(DiffModelError(
                self.tr("The working directory is clean."),
                self.tr("There aren’t any changes to commit."),
                QStyle.StandardPixmap.SP_MessageBoxInformation))
            self.setFinalLocator(locator.replace(path=""))
            yield from self._flowStop()

        return locator

    def loadCommit(self, locator: NavLocator, warnIfMissing: bool):
        rw = self.rw

        # Select row in commit log
        with QSignalBlockerContext(rw.graphView, rw.sidebar):
            commitFound = rw.graphView.selectCommit(locator.commit, silent=not warnIfMissing)

        # Commit is gone (hidden or not loaded yet)
        if not commitFound:
            yield from self._flowAbort()

        flv = rw.committedFiles

        if flv.commitOid == locator.commit:
            # No need to reload the same commit
            pass

        else:
            # Attempt to select matching ref in sidebar
            with QSignalBlockerContext(rw.sidebar):
                rw.sidebar.selectAnyRef(*rw.state.reverseRefCache.get(locator.commit, []))

            # Load commit (async)
            subtask: tasks.LoadCommit = yield from self._flowSubtask(tasks.LoadCommit, locator.commit)

            # Get data from subtask
            diffs = subtask.diffs
            summary = subtask.message.strip()

            # Fill committed file list
            with QSignalBlockerContext(flv):
                flv.clear()
                flv.setCommit(locator.commit)
                flv.setContents(diffs)
                numChanges = flv.model().rowCount()

            # Show message if commit is empty
            if flv.isEmpty():
                rw.diffStack.setCurrentWidget(rw.richDiffView)
                rw.richDiffView.displayDiffModelError(DiffModelError(self.tr("Empty commit.")))

            # Set header text
            rw.committedHeader.setText(self.tr("%n change(s) in {0}:", "", numChanges
                                               ).format(shortHash(locator.commit)))
            rw.committedHeader.setToolTip("<p>" + escape(summary).replace("\n", "<br>"))

        # Special case if there are no changes
        if flv.isEmpty():
            rw.filesStack.setCurrentWidget(rw.committedFilesContainer)
            rw.diffStack.setCurrentWidget(rw.richDiffView)
            rw.diffHeader.setText(self.tr("Empty commit"))
            rw.richDiffView.displayDiffModelError(DiffModelError(
                self.tr("This commit is empty."),
                self.tr("Commit “{0}” doesn’t affect any files.").format(shortHash(locator.commit)),
                QStyle.StandardPixmap.SP_MessageBoxInformation))
            self.setFinalLocator(locator.replace(path=""))
            yield from self._flowStop()

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
        from gitfourchette.widgets.repowidget import RepoWidget

        rw: RepoWidget = self.parentWidget()
        assert isinstance(rw, RepoWidget)

        start = rw.saveFilePositions()

        while rw.navHistory.canGoDelta(delta):
            locator = rw.navHistory.navigateDelta(delta)

            # Keep going if same file comes up several times in a row
            if locator.similarEnoughTo(start):
                continue

            yield from self._flowSubtask(Jump, locator, backup=False)

            # Navigation is deemed to be successful if the RepoWidget's final locator
            # is similar enough to the one from the history.
            if rw.navLocator.similarEnoughTo(locator):
                break

            # This locator is stale, nuke it and keep going
            rw.navHistory.popCurrent()
