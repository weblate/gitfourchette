from gitfourchette import porcelain
from gitfourchette import settings
from gitfourchette.actionflows import ActionFlows
from gitfourchette.benchmark import Benchmark
from gitfourchette.filewatcher import FileWatcher
from gitfourchette.globalstatus import globalstatus
from gitfourchette.navhistory import NavHistory, NavPos
from gitfourchette.qt import *
from gitfourchette.repostate import RepoState
from gitfourchette.stagingstate import StagingState
from gitfourchette.trash import Trash
from gitfourchette.util import (excMessageBox, excStrings, QSignalBlockerContext, shortHash,
                                showWarning, showInformation, askConfirmation, stockIcon)
from gitfourchette.widgets.brandeddialog import showTextInputDialog
from gitfourchette.widgets.conflictview import ConflictView
from gitfourchette.widgets.diffmodel import DiffModel, DiffModelError, DiffConflict, DiffImagePair, ShouldDisplayPatchAsImageDiff
from gitfourchette.widgets.diffview import DiffView
from gitfourchette.widgets.filelist import FileList, DirtyFiles, StagedFiles, CommittedFiles, FileListModel
from gitfourchette.widgets.graphview import GraphView
from gitfourchette.widgets.remotelinkprogressdialog import RemoteLinkProgressDialog
from gitfourchette.widgets.richdiffview import RichDiffView
from gitfourchette.widgets.sidebar import Sidebar
from gitfourchette.workqueue import WorkQueue
from html import escape
import os
import pygit2


def sanitizeSearchTerm(x):
    if not x:
        return None
    return x.strip().lower()


class RepoWidget(QWidget):
    nameChange: Signal = Signal()

    state: RepoState
    actionFlows: ActionFlows
    pathPending: str | None  # path of the repository if it isn't loaded yet (state=None)

    previouslySearchedTerm: str
    previouslySearchedTermInDiff: str

    navPos: NavPos
    navHistory: NavHistory

    scheduledRefresh: QTimer

    @property
    def repo(self) -> pygit2.Repository:
        return self.state.repo

    @property
    def isLoaded(self):
        return self.state is not None

    @property
    def workdir(self):
        if self.state:
            return os.path.normpath(self.state.repo.workdir)
        else:
            return self.pathPending

    @property
    def fileWatcher(self) -> FileWatcher:
        return self.state.fileWatcher

    def __init__(self, parent, sharedSplitterStates=None):
        super().__init__(parent)

        # Use workQueue to schedule operations on the repository
        # to run on a thread separate from the UI thread.
        self.workQueue = WorkQueue(self, maxThreadCount=1)

        self.state = None
        self.actionFlows = ActionFlows(None, self)
        self.pathPending = None

        self.scheduledRefresh = QTimer(self)
        self.scheduledRefresh.setSingleShot(True)
        self.scheduledRefresh.setInterval(1000)
        self.scheduledRefresh.timeout.connect(self.quickRefresh)

        self.navPos = NavPos()
        self.navHistory = NavHistory()

        self.sidebar = Sidebar(self)
        self.graphView = GraphView(self)
        self.filesStack = QStackedWidget()
        self.diffStack = QStackedWidget()
        self.committedFiles = CommittedFiles(self)
        self.dirtyFiles = DirtyFiles(self)
        self.stagedFiles = StagedFiles(self)
        self.diffView = DiffView(self)
        self.richDiffView = RichDiffView(self)
        self.conflictView = ConflictView(self)

        # The staged files and unstaged files view are mutually exclusive.
        self.stagedFiles.entryClicked.connect(self.dirtyFiles.clearSelectionSilently)
        self.dirtyFiles.entryClicked.connect(self.stagedFiles.clearSelectionSilently)

        # Refresh file list views after applying a patch from the diff view (partial line patch)
        self.diffView.patchApplied.connect(lambda: self.fillStageViewAsync(allowUpdateIndex=True))
        # Note that refreshing the file list views may, in turn, re-select a file from the appropriate file view,
        # which will trigger the diff view to be refreshed as well.

        self.stagedFiles.unstageFiles.connect(self.unstageFilesAsync)
        self.dirtyFiles.stageFiles.connect(self.stageFilesAsync)
        self.dirtyFiles.discardFiles.connect(self.actionFlows.discardFilesFlow)  # we need to confirm deletions

        for v in [self.dirtyFiles, self.stagedFiles, self.committedFiles]:
            v.nothingClicked.connect(self.diffView.clear)
            v.entryClicked.connect(self.loadPatchAsync)

        self.conflictView.hardSolve.connect(lambda path, oid: self.hardSolveConflictAsync(path, oid))
        self.conflictView.markSolved.connect(lambda path: self.markConflictSolvedAsync(path))
        self.conflictView.openFile.connect(lambda path: self.openConflictFile(path))

        self.graphView.emptyClicked.connect(self.setNoCommitSelected)
        self.graphView.commitClicked.connect(self.loadCommitAsync)
        self.graphView.uncommittedChangesClicked.connect(self.fillStageViewAsync)
        self.graphView.resetHead.connect(self.resetHeadAsync)
        self.graphView.newBranchFromCommit.connect(self.actionFlows.newBranchFromCommitFlow)
        self.graphView.checkoutCommit.connect(self.checkoutCommitAsync)
        self.graphView.revertCommit.connect(self.revertCommitAsync)

        self.sidebar.commit.connect(self.startCommitFlow)
        self.sidebar.commitClicked.connect(self.graphView.selectCommit)
        self.sidebar.deleteBranch.connect(self.actionFlows.deleteBranchFlow)
        self.sidebar.deleteRemote.connect(self.actionFlows.deleteRemoteFlow)
        self.sidebar.editRemote.connect(self.actionFlows.editRemoteFlow)
        self.sidebar.editTrackingBranch.connect(self.actionFlows.editTrackingBranchFlow)
        self.sidebar.fetchRemote.connect(self.fetchRemoteAsync)
        self.sidebar.fetchRemoteBranch.connect(self.fetchRemoteBranchAsync)
        self.sidebar.renameRemoteBranch.connect(self.actionFlows.renameRemoteBranchFlow)
        self.sidebar.deleteRemoteBranch.connect(self.actionFlows.deleteRemoteBranchFlow)
        self.sidebar.pushBranch.connect(self.actionFlows.pushFlow)
        self.sidebar.pullBranch.connect(self.actionFlows.pullFlow)
        self.sidebar.newBranch.connect(self.actionFlows.newBranchFlow)
        self.sidebar.newBranchFromBranch.connect(self.actionFlows.newBranchFromBranchFlow)
        self.sidebar.newRemote.connect(self.actionFlows.newRemoteFlow)
        self.sidebar.newTrackingBranch.connect(self.actionFlows.newTrackingBranchFlow)
        self.sidebar.refClicked.connect(self.selectRef)
        self.sidebar.renameBranch.connect(self.actionFlows.renameBranchFlow)
        self.sidebar.switchToBranch.connect(self.switchToBranchAsync)
        self.sidebar.uncommittedChangesClicked.connect(self.graphView.selectUncommittedChanges)
        self.sidebar.toggleHideBranch.connect(self.toggleHideBranch)

        self.sidebar.newStash.connect(self.actionFlows.newStashFlow)
        self.sidebar.applyStash.connect(self.applyStashAsync)
        self.sidebar.dropStash.connect(self.dropStashAsync)
        self.sidebar.popStash.connect(self.popStashAsync)

        self.sidebar.openSubmoduleRepo.connect(self.openSubmoduleRepo)
        self.sidebar.openSubmoduleFolder.connect(self.openSubmoduleFolder)

        # ----------------------------------

        flows = self.actionFlows

        flows.amendCommit.connect(self.amendCommitAsync)
        flows.createCommit.connect(self.createCommitAsync)
        flows.deleteBranch.connect(self.deleteBranchAsync)
        flows.deleteRemote.connect(self.deleteRemoteAsync)
        flows.deleteRemoteBranch.connect(self.deleteRemoteBranchAsync)
        flows.discardFiles.connect(self.discardFilesAsync)
        flows.editRemote.connect(self.editRemoteAsync)
        flows.editTrackingBranch.connect(self.editTrackingBranchAsync)
        flows.newBranch.connect(self.newBranchAsync)
        flows.newRemote.connect(self.newRemoteAsync)
        flows.newStash.connect(self.newStashAsync)
        flows.newTrackingBranch.connect(self.newTrackingBranchAsync)
        flows.renameBranch.connect(self.renameBranchAsync)
        flows.renameRemoteBranch.connect(self.renameRemoteBranchAsync)
        flows.pullBranch.connect(self.pullBranchAsync)
        flows.updateCommitDraftMessage.connect(lambda message: self.state.setDraftCommitMessage(message))

        flows.pushComplete.connect(self.quickRefreshWithSidebar)

        # ----------------------------------

        self.splitterStates = sharedSplitterStates or {}

        self.dirtyLabel = QLabel("Dirty Files")
        self.stageLabel = QLabel("Files Staged For Commit")

        self.previouslySearchedTerm = None
        self.previouslySearchedTermInDiff = None

        dirtyContainer = QWidget()
        dirtyContainer.setLayout(QVBoxLayout())
        dirtyContainer.layout().setContentsMargins(0, 0, 0, 0)
        dirtyContainer.layout().addWidget(self.dirtyLabel)
        dirtyContainer.layout().addWidget(self.dirtyFiles)
        stageContainer = QWidget()
        stageContainer.setLayout(QVBoxLayout())
        stageContainer.layout().setContentsMargins(0, 0, 0, 0)
        stageContainer.layout().addWidget(self.stageLabel)
        stageContainer.layout().addWidget(self.stagedFiles)
        commitButtonsContainer = QWidget()
        commitButtonsContainer.setLayout(QHBoxLayout())
        commitButtonsContainer.layout().setContentsMargins(0, 0, 0, 0)
        stageContainer.layout().addWidget(commitButtonsContainer)
        self.commitButton = QPushButton(self.tr("&Commit"))
        self.commitButton.clicked.connect(self.startCommitFlow)
        self.amendButton = QPushButton(self.tr("&Amend"))
        self.amendButton.clicked.connect(self.actionFlows.amendFlow)
        commitButtonsContainer.layout().addWidget(self.commitButton)
        commitButtonsContainer.layout().addWidget(self.amendButton)
        self.stageSplitter = QSplitter(Qt.Orientation.Vertical)
        self.stageSplitter.addWidget(dirtyContainer)
        self.stageSplitter.addWidget(stageContainer)

        self.filesStack.addWidget(self.committedFiles)
        self.filesStack.addWidget(self.stageSplitter)
        self.filesStack.setCurrentWidget(self.committedFiles)

        self.diffStack.addWidget(self.diffView)
        self.diffStack.addWidget(self.richDiffView)
        self.diffStack.addWidget(self.conflictView)
        self.diffStack.setCurrentWidget(self.diffView)

        bottomSplitter = QSplitter(Qt.Orientation.Horizontal)
        bottomSplitter.addWidget(self.filesStack)
        bottomSplitter.addWidget(self.diffStack)
        bottomSplitter.setSizes([100, 300])

        mainSplitter = QSplitter(Qt.Orientation.Vertical)
        mainSplitter.addWidget(self.graphView)
        mainSplitter.addWidget(bottomSplitter)
        mainSplitter.setSizes([100, 150])

        sideSplitter = QSplitter(Qt.Orientation.Horizontal)
        sideSplitter.addWidget(self.sidebar)
        sideSplitter.addWidget(mainSplitter)
        sideSplitter.setSizes([100, 500])
        sideSplitter.setStretchFactor(0, 0)  # don't auto-stretch sidebar when resizing window
        sideSplitter.setStretchFactor(1, 1)

        self.setLayout(QVBoxLayout())
        self.layout().setSpacing(0)
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().addWidget(sideSplitter)

        # object names are required for state saving to work
        mainSplitter.setObjectName("MainSplitter")
        bottomSplitter.setObjectName("BottomSplitter")
        self.stageSplitter.setObjectName("StageSplitter")
        sideSplitter.setObjectName("SideSplitter")
        self.splittersToSave = [mainSplitter, bottomSplitter, self.stageSplitter, sideSplitter]
        # save splitter state in splitterMoved signal
        for splitter in self.splittersToSave:
            splitter.splitterMoved.connect(lambda pos, index, splitter=splitter: self.saveSplitterState(splitter))

        # remove frames for a cleaner look
        #for w in self.graphView, self.diffView, self.dirtyView, self.stageView, self.changedFilesView, self.sidebar:
        #    w.setFrameStyle(QFrame.Shape.NoFrame)
        self.sidebar.setFrameStyle(QFrame.Shape.NoFrame)

    # -------------------------------------------------------------------------

    def setRepoState(self, state: RepoState):
        if state:
            self.state = state
            self.state.fileWatcher.setParent(self)
            self.state.fileWatcher.directoryChanged.connect(self.onDirectoryChange)
            self.state.fileWatcher.indexChanged.connect(self.onIndexChange)
            self.actionFlows.repo = state.repo
        else:
            self.state = None
            self.actionFlows.repo = None

    def installFileWatcher(self, intervalMS=100):
        self.state.fileWatcher.boot(intervalMS)
        self.scheduledRefresh.setInterval(intervalMS)

    def stopFileWatcher(self):
        self.state.fileWatcher.shutdown()

    def onDirectoryChange(self):
        globalstatus.setText(self.tr("Detected external change..."))

        if self.scheduledRefresh.interval() == 0:
            # Just fire it now if instantaneous
            # TODO: Do we need this one? There's already a delay in FSW
            self.scheduledRefresh.timeout.emit()
        else:
            self.scheduledRefresh.stop()
            self.scheduledRefresh.start()

    def onIndexChange(self):
        if self.isStageViewShown:
            self.quickRefresh()

    # -------------------------------------------------------------------------

    def saveSplitterState(self, splitter: QSplitter):
        self.splitterStates[splitter.objectName()] = splitter.saveState()

    def restoreSplitterStates(self):
        for splitter in self.splittersToSave:
            try:
                splitter.restoreState(self.splitterStates[splitter.objectName()])
            except KeyError:
                pass

    # -------------------------------------------------------------------------

    def saveFilePositions(self):
        if self.diffStack.currentWidget() == self.diffView:
            self.navPos.diffScroll = self.diffView.verticalScrollBar().value()
            self.navPos.diffCursor = self.diffView.textCursor().position()
        else:
            self.navPos.diffScroll = 0
            self.navPos.diffCursor = 0
        self.navHistory.push(self.navPos)

    def restoreSelectedFile(self):
        pos = self.navPos

        if not pos or not pos.context:
            return False

        if pos.context in ["UNSTAGED", "UNTRACKED"]:
            fl = self.dirtyFiles
        elif pos.context == "STAGED":
            fl = self.stagedFiles
        else:
            assert len(pos.context) == 40, "expecting an OID here"
            fl = self.committedFiles

        return fl.selectFile(pos.file)

    def restoreDiffPosition(self):
        cursorPosition = self.navPos.diffCursor
        scrollPosition = self.navPos.diffScroll

        newTextCursor = QTextCursor(self.diffView.textCursor())
        newTextCursor.setPosition(cursorPosition)
        self.diffView.setTextCursor(newTextCursor)

        self.diffView.verticalScrollBar().setValue(scrollPosition)

    def navigateTo(self, pos: NavPos):
        if not pos or not pos.context:
            QApplication.beep()
            return False

        self.navPos = pos

        self.navHistory.setRecent(pos)

        self.navHistory.lock()

        if self.navPos.context in ["UNSTAGED", "STAGED", "UNTRACKED"]:
            if self.graphView.currentCommitOid is not None:
                self.graphView.selectUncommittedChanges()
                success = True
            else:
                success = self.restoreSelectedFile()
                self.navHistory.unlock()
        else:
            oid = pygit2.Oid(hex=self.navPos.context)
            if self.graphView.currentCommitOid != oid:
                success = self.graphView.selectCommit(oid)
            else:
                success = self.restoreSelectedFile()
                self.navHistory.unlock()

        return success

    def navigateBack(self):
        if self.navHistory.isAtTopOfStack:
            self.saveFilePositions()

        startPos = self.navPos.copy()

        while not self.navHistory.isAtBottomOfStack:
            pos = self.navHistory.navigateBack()
            success = self.navigateTo(pos)

            if success and pos != startPos:
                break

    def navigateForward(self):
        startPos = self.navPos.copy()

        while not self.navHistory.isAtTopOfStack:
            pos = self.navHistory.navigateForward()
            success = self.navigateTo(pos)

            if success and pos != startPos:
                break


    # -------------------------------------------------------------------------

    def selectNextFile(self, down=True):
        if self.filesStack.currentWidget() == self.committedFiles:
            dirtyIndices = self.committedFiles.selectedIndexes()
            dirtyRowCount = self.committedFiles.model().rowCount()

            kpIndex = -1

            if dirtyIndices:
                leaderRow = dirtyIndices[-1].row()  # TODO: this may not be accurate when multiple rows are selected
                if down and leaderRow < dirtyRowCount-1:  # select next dirty file
                    kpIndex = leaderRow+1
                elif not down and leaderRow > 0:  # select prev dirty file
                    kpIndex = leaderRow-1
            elif dirtyRowCount > 0:
                kpIndex = 0
            
            if kpIndex >= 0:
                self.committedFiles.clearSelectionSilently()
                self.committedFiles.selectRow(kpIndex)
            else:
                QApplication.beep()

        elif self.filesStack.currentWidget() == self.stageSplitter:
            dirtyIndices = self.dirtyFiles.selectedIndexes()
            stagedIndices = self.stagedFiles.selectedIndexes()

            dirtyRowCount = self.dirtyFiles.model().rowCount()
            stagedRowCount = self.stagedFiles.model().rowCount()

            kpWidget = None
            kpIndex = 0

            if not dirtyIndices and not stagedIndices:
                if dirtyRowCount > 0:
                    kpWidget = self.dirtyFiles
                    kpIndex = 0
                elif stagedRowCount > 0:
                    kpWidget = self.stagedFiles
                    kpIndex = 0

            elif dirtyIndices:
                leaderRow = dirtyIndices[-1].row()  # TODO: this may not be accurate when multiple rows are selected

                if down:
                    if leaderRow < dirtyRowCount-1:  # select next dirty file
                        kpWidget = self.dirtyFiles
                        kpIndex = leaderRow+1
                    elif stagedRowCount > 0:  # out of dirty rows, move on to first row in staged box
                        kpWidget = self.stagedFiles
                        kpIndex = 0
                else:
                    if leaderRow > 0:  # select prev dirty file
                        kpWidget = self.dirtyFiles
                        kpIndex = leaderRow-1
            
            elif stagedIndices:
                leaderRow = stagedIndices[-1].row()  # TODO: this may not be accurate when multiple rows are selected

                if down:
                    if leaderRow < stagedRowCount-1:  # select next staged file
                        kpWidget = self.stagedFiles
                        kpIndex = leaderRow+1
                else:
                    if leaderRow > 0:  # select prev staged file
                        kpWidget = self.stagedFiles
                        kpIndex = leaderRow-1
                    elif dirtyRowCount > 0:  # out of staged rows, move on to last row in dirty box
                        kpWidget = self.dirtyFiles
                        kpIndex = dirtyRowCount-1
            
            if kpWidget:
                #kpWidget.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key.Key_Down if down else Qt.Key.Key_Up, Qt.KeyboardModifier.NoModifier))
                kpWidget.clearSelectionSilently()
                kpWidget.selectRow(kpIndex)
            else:
                QApplication.beep()

    # -------------------------------------------------------------------------

    def getTitle(self):
        if self.state:
            return self.state.shortName
        elif self.pathPending:
            return F"({settings.history.getRepoNickname(self.pathPending)})"
        else:
            return "???"

    def closeEvent(self, event: QCloseEvent):
        """ Called when closing a repo tab """
        self.cleanup()

    def cleanup(self):
        if self.state and self.state.repo:
            self.committedFiles.clear()
            self.dirtyFiles.clear()
            self.stagedFiles.clear()
            self.graphView.clear()
            self.clearDiffView()
            # Save path if we want to reload the repo later
            self.pathPending = os.path.normpath(self.state.repo.workdir)
            self.state.repo.free()
        if self.state and self.state.fileWatcher:
            self.state.fileWatcher.shutdown()
        self.setRepoState(None)

    def clearDiffView(self):
        self.diffView.clear()
        self.diffStack.setCurrentWidget(self.diffView)

    def setPendingWorkdir(self, path):
        self.pathPending = os.path.normpath(path)

    def startCommitFlow(self):
        initialMessage = self.state.getDraftCommitMessage()
        self.actionFlows.commitFlow(initialMessage)

    def renameRepo(self):
        def onAccept(newName):
            settings.history.setRepoNickname(self.workdir, newName)
            settings.history.write()
            self.nameChange.emit()
        showTextInputDialog(
            self,
            self.tr("Edit repo nickname"),
            self.tr("Enter new nickname for repo, or enter blank line to reset:"),
            settings.history.getRepoNickname(self.workdir),
            onAccept,
            okButtonText=self.tr("Rename", "edit repo nickname"))

    def setNoCommitSelected(self):
        self.saveFilePositions()
        self.navPos = NavPos()

        self.filesStack.setCurrentWidget(self.stageSplitter)
        self.committedFiles.clear()

        self.clearDiffView()

    def fillStageViewAsync(self, forceSelectFile: NavPos = None, allowUpdateIndex: bool = False):
        """Fill Staged/Unstaged views with uncommitted changes"""

        repo = self.state.repo

        def work() -> tuple[pygit2.Diff, pygit2.Diff]:
            porcelain.refreshIndex(repo)
            dirtyDiff = porcelain.diffWorkdirToIndex(repo, allowUpdateIndex)
            stageDiff = porcelain.diffIndexToHead(repo)
            return dirtyDiff, stageDiff

        def then(result: tuple[pygit2.Diff, pygit2.Diff]):
            dirtyDiff, stageDiff = result

            # Reset dirty & stage views. Block their signals as we refill them to prevent updating the diff view.
            with QSignalBlockerContext(self.dirtyFiles), QSignalBlockerContext(self.stagedFiles):
                self.dirtyFiles.clear()
                self.stagedFiles.clear()
                self.dirtyFiles.setContents([dirtyDiff])
                self.stagedFiles.setContents([stageDiff])

            nDirty = self.dirtyFiles.model().rowCount()
            nStaged = self.stagedFiles.model().rowCount()
            self.dirtyLabel.setText(self.tr("%n dirty file(s):", "", nDirty))
            self.stageLabel.setText(self.tr("%n file(s) staged for commit:", "", nStaged))

            # Switch to correct card in filesStack to show dirtyView and stageView
            self.filesStack.setCurrentWidget(self.stageSplitter)

            if forceSelectFile:  # for Revert Hunk from DiffView
                self.navPos = forceSelectFile

            # After patchApplied.emit has caused a refresh of the dirty/staged file views,
            # restore selected row in appropriate file list view so the user can keep hitting
            # enter (del) to stage (unstage) a series of files.
            if not self.restoreSelectedFile():
                if stagedESR >= 0:
                    self.stagedFiles.selectRow(min(stagedESR, self.stagedFiles.model().rowCount()-1))
                elif dirtyESR >= 0:
                    self.dirtyFiles.selectRow(min(dirtyESR, self.dirtyFiles.model().rowCount()-1))

            # If no file is selected in either FileListView, clear the diffView of any residual diff.
            if 0 == (len(self.dirtyFiles.selectedIndexes()) + len(self.stagedFiles.selectedIndexes())):
                self.clearDiffView()

            self.navHistory.unlock()

        stagedESR = self.stagedFiles.earliestSelectedRow()
        dirtyESR = self.dirtyFiles.earliestSelectedRow()

        self.saveFilePositions()

        opName = translate("Operation", "Refresh working directory")
        self.workQueue.put(work, then, opName, -1000)

    def loadCommitAsync(self, oid: pygit2.Oid):
        """Load commit details into Changed Files view"""

        work = lambda: porcelain.loadCommitDiffs(self.repo, oid)

        def then(parentDiffs: list[pygit2.Diff]):
            #import time; time.sleep(1) #to debug out-of-order events

            # Reset changed files view. Block its signals as we refill it to prevent updating the diff view.
            with QSignalBlockerContext(self.committedFiles):
                self.committedFiles.clear()
                self.committedFiles.setCommit(oid)
                self.committedFiles.setContents(parentDiffs)

            self.navPos = self.navHistory.findContext(oid.hex)
            if not self.navPos:
                self.navPos = NavPos(context=oid.hex, file=self.committedFiles.getFirstPath())

            # Show message if commit is empty
            if self.committedFiles.flModel.rowCount() == 0:
                self.diffStack.setCurrentWidget(self.richDiffView)
                self.richDiffView.displayDiffModelError(DiffModelError(self.tr("Empty commit.")))

            # Switch to correct card in filesStack to show changedFilesView
            self.filesStack.setCurrentWidget(self.committedFiles)

            self.restoreSelectedFile()

        self.saveFilePositions()

        opName = translate("Operation", "Load commit “{0}”").format(shortHash(oid))
        self.workQueue.put(work, then, opName, -1000)

    def loadPatchAsync(self, patch: pygit2.Patch, stagingState: StagingState):
        """Load a file diff into the pygit2.Diff View"""

        if not patch:
            self.diffStack.setCurrentWidget(self.richDiffView)
            self.richDiffView.displayDiffModelError(DiffModelError(
                self.tr("Patch is invalid."),
                self.tr("The patched file may have changed on disk since we last read it. Try refreshing the window."),
                icon=QStyle.StandardPixmap.SP_MessageBoxWarning))
            return

        repo = self.state.repo

        def work():
            if patch.delta.status == pygit2.GIT_DELTA_CONFLICTED:
                ancestor, ours, theirs = repo.index.conflicts[patch.delta.new_file.path]
                return DiffConflict(repo, ancestor, ours, theirs)

            try:
                dm = DiffModel.fromPatch(patch)
                dm.document.moveToThread(QApplication.instance().thread())
                return dm
            except DiffModelError as dme:
                return dme
            except ShouldDisplayPatchAsImageDiff:
                return DiffImagePair(self.repo, patch.delta, stagingState)
            except BaseException as exc:
                summary, details = excStrings(exc)
                return DiffModelError(summary, icon=QStyle.StandardPixmap.SP_MessageBoxCritical, preformatted=details)

        def then(result: DiffModel | DiffModelError | DiffImagePair):
            if stagingState == StagingState.COMMITTED:
                assert len(self.navPos.context) == 40
                posContext = self.navPos.context
            else:
                posContext = stagingState.name
            posFile = patch.delta.new_file.path
            self.navPos = self.navHistory.findFileInContext(posContext, posFile)
            if not self.navPos:
                self.navPos = NavPos(posContext, posFile)

            if type(result) == DiffConflict:
                self.diffStack.setCurrentWidget(self.conflictView)
                self.conflictView.displayConflict(result)
            elif type(result) == DiffModelError:
                self.diffStack.setCurrentWidget(self.richDiffView)
                self.richDiffView.displayDiffModelError(result)
            elif type(result) == DiffModel:
                self.diffStack.setCurrentWidget(self.diffView)
                self.diffView.replaceDocument(repo, patch, stagingState, result)
                self.restoreDiffPosition()  # restore position after we've replaced the document
            elif type(result) == DiffImagePair:
                self.diffStack.setCurrentWidget(self.richDiffView)
                self.richDiffView.displayImageDiff(patch.delta, result.oldImage, result.newImage)
            else:
                self.diffStack.setCurrentWidget(self.richDiffView)
                self.richDiffView.displayDiffModelError(DiffModelError(
                    self.tr("Can’t display diff of type {0}.").format(escape(str(type(result)))),
                    icon=QStyle.StandardPixmap.SP_MessageBoxCritical))

        self.saveFilePositions()

        opName = translate("Operation", "Load diff “{0}”").format(patch.delta.new_file.path)
        self.workQueue.put(work, then, opName, -500)

    def createCommitAsync(self, message: str, author: pygit2.Signature | None, committer: pygit2.Signature | None):
        def work():
            porcelain.createCommit(self.repo, message, author, committer)

        def then(_):
            self.state.setDraftCommitMessage(None)  # Clear draft message
            self.quickRefreshWithSidebar()

        # Save commit message as draft now, so we don't lose it if the commit fails.
        self.state.setDraftCommitMessage(message)

        opName = translate("Operation", "Commit")
        self.workQueue.put(work, then, opName)

    def amendCommitAsync(self, message: str, author: pygit2.Signature | None, committer: pygit2.Signature | None):
        def work():
            porcelain.amendCommit(self.repo, message, author, committer)

        def then(_):
            self.quickRefreshWithSidebar()

        opName = translate("Operation", "Amend commit")
        self.workQueue.put(work, then, opName)

    def switchToBranchAsync(self, newBranch: str):
        assert not newBranch.startswith("refs/heads/")

        work = lambda: porcelain.checkoutLocalBranch(self.repo, newBranch)
        then = lambda _: self.quickRefreshWithSidebar()

        opName = translate("Operation", "Switch to branch “{0}”").format(newBranch)
        self.workQueue.put(work, then, opName)

    def renameBranchAsync(self, oldName: str, newName: str):
        assert not oldName.startswith("refs/heads/")

        work = lambda: porcelain.renameBranch(self.repo, oldName, newName)
        then = lambda _: self.quickRefreshWithSidebar()

        opName = translate("Operation", "Rename local branch “{0}”").format(oldName)
        self.workQueue.put(work, then, opName)

    def deleteBranchAsync(self, localBranchName: str):
        assert not localBranchName.startswith("refs/heads/")

        work = lambda: porcelain.deleteBranch(self.repo, localBranchName)
        then = lambda _: self.quickRefreshWithSidebar()

        opName = translate("Operation", "Delete local branch “{0}”").format(localBranchName)
        self.workQueue.put(work, then, opName)

    def newBranchAsync(self, localBranchName: str, tip: pygit2.Oid, tracking: str, switchTo: bool):
        assert not localBranchName.startswith("refs/heads/")

        def work():
            porcelain.newBranchFromCommit(self.repo, localBranchName, tip, switchTo=False)
            if tracking:
                porcelain.editTrackingBranch(self.repo, localBranchName, tracking)
            # Switch last
            if switchTo:
                porcelain.checkoutLocalBranch(self.repo, localBranchName)

        def then(_): self.quickRefreshWithSidebar()

        opName = translate("Operation", "Create local branch “{0}”").format(localBranchName)
        self.workQueue.put(work, then, opName)

    def newTrackingBranchAsync(self, localBranchName: str, remoteBranchName: str):
        assert not localBranchName.startswith("refs/heads/")

        work = lambda: porcelain.newTrackingBranch(self.repo, localBranchName, remoteBranchName)
        then = lambda _: self.quickRefreshWithSidebar()

        opName = translate("Operation", "New branch “{0}”").format(localBranchName)
        self.workQueue.put(work, then, opName)

    def editTrackingBranchAsync(self, localBranchName: str, remoteBranchName: str):
        work = lambda: porcelain.editTrackingBranch(self.repo, localBranchName, remoteBranchName)
        then = lambda _: self.quickRefreshWithSidebar()

        opName = translate("Operation", "Change remote branch tracked by “{0}”").format(localBranchName)
        self.workQueue.put(work, then, opName)

    def newRemoteAsync(self, name: str, url: str):
        work = lambda: porcelain.newRemote(self.repo, name, url)
        then = lambda _: self.quickRefreshWithSidebar()

        opName = translate("Operation", "Add remote “{0}”").format(name)
        self.workQueue.put(work, then, opName)

    def editRemoteAsync(self, remoteName: str, newName: str, newURL: str):
        work = lambda: porcelain.editRemote(self.repo, remoteName, newName, newURL)
        then = lambda _: self.quickRefreshWithSidebar()

        opName = translate("Operation", "Edit remote “{0}”").format(remoteName)
        self.workQueue.put(work, then, opName)

    def fetchRemoteAsync(self, remoteName: str):
        rlpd = RemoteLinkProgressDialog(self)

        def work():
            return porcelain.fetchRemote(self.repo, remoteName, rlpd.remoteLink)

        def then(_):
            rlpd.close()
            self.quickRefreshWithSidebar()

        def onError(exc):
            rlpd.close()
            excMessageBox(exc, parent=self, title=opName, message=self.tr("Couldn’t fetch remote “{0}”.").format(escape(remoteName)))

        opName = translate("Operation", "Fetch remote “{0}”").format(remoteName)
        self.workQueue.put(work, then, opName, errorCallback=onError)

    def fetchRemoteBranchAsync(self, remoteBranchName: str):
        rlpd = RemoteLinkProgressDialog(self)

        def work():
            return porcelain.fetchRemoteBranch(self.repo, remoteBranchName, rlpd.remoteLink)

        def then(_):
            rlpd.close()
            self.quickRefreshWithSidebar()

        def onError(exc):
            rlpd.close()
            excMessageBox(exc, parent=self, title=opName, message=self.tr("Couldn’t fetch remote branch “{0}”.").format(remoteBranchName))

        opName = translate("Operation", "Fetch remote branch “{0}”").format(remoteBranchName)
        self.workQueue.put(work, then, opName, errorCallback=onError)

    def deleteRemoteAsync(self, remoteName: str):
        work = lambda: porcelain.deleteRemote(self.repo, remoteName)
        then = lambda _: self.quickRefreshWithSidebar()

        opName = translate("Operation", "Delete remote “{0}”").format(remoteName)
        self.workQueue.put(work, then, opName)

    def deleteRemoteBranchAsync(self, remoteBranchName: str):
        rlpd = RemoteLinkProgressDialog(self)

        def work():
            return porcelain.deleteRemoteBranch(self.repo, remoteBranchName, rlpd.remoteLink)

        def then(_):
            rlpd.close()
            self.quickRefreshWithSidebar()

        def onError(exc):
            rlpd.close()
            excMessageBox(exc, parent=self, title=opName, message=self.tr("Couldn’t delete remote branch “{0}”.").format(remoteBranchName))

        opName = translate("Operation", "Delete remote branch “{0}”").format(remoteBranchName)
        self.workQueue.put(work, then, opName, errorCallback=onError)

    def renameRemoteBranchAsync(self, remoteBranchName: str, newName: str):
        rlpd = RemoteLinkProgressDialog(self)

        def work():
            return porcelain.renameRemoteBranch(self.repo, remoteBranchName, newName, rlpd.remoteLink)

        def then(_):
            rlpd.close()
            self.quickRefreshWithSidebar()

        def onError(exc):
            rlpd.close()
            excMessageBox(exc, parent=self, title=opName, message=self.tr("Couldn’t rename remote branch “{0}”.").format(remoteBranchName))

        opName = translate("Operation", "Rename remote branch “{0}”").format(remoteBranchName)
        self.workQueue.put(work, then, opName, errorCallback=onError)

    def resetHeadAsync(self, onto: pygit2.Oid, resetMode: str, recurseSubmodules: bool):
        work = lambda: porcelain.resetHead(self.repo, onto, resetMode, recurseSubmodules)
        def then(_):
            self.quickRefreshWithSidebar()
            self.graphView.selectCommit(onto)

        opName = translate("Operation", "Reset HEAD onto “{0}” ({1})").format(shortHash(onto), resetMode)
        self.workQueue.put(work, then, opName)

    def stageFilesAsync(self, patches: list[pygit2.Patch]):
        def work():
            with self.fileWatcher.blockWatchingIndex():
                porcelain.stageFiles(self.repo, patches)

        def then(_):
            self.fillStageViewAsync(allowUpdateIndex=True)

        numPatches = len(patches)  # Work around Qt Linguist parsing bug -- but it fails to pick up the numerus anyway...
        opName = QCoreApplication.translate("Operation", "Stage %n file(s)", "", numPatches)

        self.workQueue.put(work, then, opName)

    def discardFilesAsync(self, patches: list[pygit2.Patch]):
        def work():
            paths = [patch.delta.new_file.path for patch in patches]
            Trash(self.repo).backupPatches(patches)
            porcelain.discardFiles(self.repo, paths)

        def then(_):
            self.fillStageViewAsync(allowUpdateIndex=True)

        numPatches = len(patches)  # Work around Qt Linguist parsing bug -- but it fails to pick up the numerus anyway...
        opName = translate("Operation", "Discard %n file(s)", "", numPatches)

        self.workQueue.put(work, then, opName)

    def unstageFilesAsync(self, patches: list[pygit2.Patch]):
        def work():
            with self.fileWatcher.blockWatchingIndex():
                porcelain.unstageFiles(self.repo, patches)

        def then(_):
            self.fillStageViewAsync(allowUpdateIndex=True)

        numPatches = len(patches)  # Work around Qt Linguist parsing bug -- but it fails to pick up the numerus anyway...
        opName = translate("Operation", "Unstage %n file(s)", "", numPatches)

        self.workQueue.put(work, then, opName)

    def newStashAsync(self, message: str, flags: str):
        def work():
            with self.fileWatcher.blockWatchingIndex():
                return porcelain.newStash(self.repo, message, flags)

        def then(_):
            self.quickRefreshWithSidebar()

        opName = translate("Operation", "New stash")
        self.workQueue.put(work, then, opName)

    def applyStashAsync(self, commitId: pygit2.Oid):
        def work(): porcelain.applyStash(self.repo, commitId)
        then = lambda _: self.quickRefreshWithSidebar()
        opName = translate("Operation", "Apply stash")
        self.workQueue.put(work, then, opName,
                           errorCallback=lambda exc: self._processCheckoutError(exc, opName))

    def popStashAsync(self, commitId: pygit2.Oid):
        def work(): porcelain.popStash(self.repo, commitId)
        then = lambda _: self.quickRefreshWithSidebar()
        opName = translate("Operation", "Pop stash")
        self.workQueue.put(work, then, opName,
                           errorCallback=lambda exc: self._processCheckoutError(exc, opName))

    def dropStashAsync(self, commitId: pygit2.Oid):
        def work(): porcelain.dropStash(self.repo, commitId)
        then = lambda _: self.quickRefreshWithSidebar()
        opName = translate("Operation", "Delete stash")
        self.workQueue.put(work, then, opName)

    def openSubmoduleRepo(self, submoduleKey: str):
        path = porcelain.getSubmoduleWorkdir(self.repo, submoduleKey)
        self.window().openRepo(path)
        self.window().saveSession()

    def openSubmoduleFolder(self, submoduleKey: str):
        path = porcelain.getSubmoduleWorkdir(self.repo, submoduleKey)
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _processCheckoutError(self, exc, opName="Operation"):
        if isinstance(exc, porcelain.ConflictError):
            maxConflicts = 10
            numConflicts = len(exc.conflicts)

            title = self.tr("%n conflicting file(s)", "", numConflicts)

            if exc.description == "workdir":
                message = self.tr("Operation <b>{0}</b> conflicts with the working directory.").format(opName)
            elif exc.description == "HEAD":
                message = self.tr("Operation <b>{0}</b> conflicts with the commit at HEAD.").format(opName)
            else:
                message = self.tr("Operation <b>{0}</b> caused a conflict ({1}).").format(opName, exc.description)

            message += f"<br><br>{title}:<ul><li>"

            message += "</li><li>".join(exc.conflicts[:maxConflicts])

            if numConflicts > maxConflicts:
                message += "</li></ul>"
                message += self.tr("... and %n more", "", (numConflicts - maxConflicts))

            showWarning(self, title, message)
        else:
            raise exc

    def checkoutCommitAsync(self, oid: pygit2.Oid):
        oldCommit = self.state.activeCommitOid

        def work():
            porcelain.checkoutCommit(self.repo, oid)

        def then(_):
            self.quickRefreshWithSidebar()
            self.graphView.repaintCommit(oldCommit)
            self.graphView.repaintCommit(oid)

        opName = translate("Operation", "Check out commit “{0}”").format(shortHash(oid))
        self.workQueue.put(work, then, opName,
                           errorCallback=lambda exc: self._processCheckoutError(exc, opName))

    def revertCommitAsync(self, oid: pygit2.Oid):
        def work():
            porcelain.revertCommit(self.repo, oid)

        def then(_):
            self.quickRefreshWithSidebar()

        opName = translate("Operation", "Revert commit “{0}”").format(shortHash(oid))
        self.workQueue.put(work, then, opName,
                           errorCallback=lambda exc: self._processCheckoutError(exc, opName))

    # -------------------------------------------------------------------------
    # Pull

    def pullBranchAsync(self, localBranchName: str, remoteBranchName: str):
        def work():
            porcelain.pull(self.repo, localBranchName, remoteBranchName)

        def then(_):
            self.quickRefreshWithSidebar()

        opName = translate("Operation", "Pull branch “{0}”").format(localBranchName)

        def onError(exc):
            if isinstance(exc, porcelain.DivergentBranchesError):
                showWarning(self, opName,
                            self.tr("Can’t fast-forward: You have divergent branches."))
            else:
                self._processCheckoutError(exc, opName)

        self.workQueue.put(work, then, opName, errorCallback=onError)

    # -------------------------------------------------------------------------
    # Conflicts

    def hardSolveConflictAsync(self, path: str, keepOid: pygit2.Oid):
        repo = self.repo

        def work():
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

        def then(_):
            self.quickRefreshWithSidebar()

        opName = translate("Operation", "Hard solve conflict")
        self.workQueue.put(work, then, opName)

    def markConflictSolvedAsync(self, path: str):
        repo = self.repo

        def work():
            porcelain.refreshIndex(repo)
            assert (repo.index.conflicts is not None) and (path in repo.index.conflicts)

            del repo.index.conflicts[path]
            assert (repo.index.conflicts is None) or (path not in repo.index.conflicts)
            repo.index.write()

        def then(_):
            self.quickRefreshWithSidebar()

        opName = translate("Operation", "Mark conflict solved")
        self.workQueue.put(work, then, opName)

    def openConflictFile(self, path: str):
        fullPath = os.path.join(self.repo.workdir, path)
        QDesktopServices.openUrl(QUrl.fromLocalFile(fullPath))

    # -------------------------------------------------------------------------
    # Find, find next

    def _search(self, searchRange):
        message = self.previouslySearchedTerm
        message = sanitizeSearchTerm(message)
        if not message:
            showWarning(self, self.tr("Find Commit"), self.tr("Invalid search term."))
            return

        likelyHash = False
        if len(message) <= 40:
            try:
                int(message, 16)
                likelyHash = True
            except ValueError:
                pass

        model = self.graphView.model()

        for i in searchRange:
            modelIndex = model.index(i, 0)
            meta = model.data(modelIndex)
            if meta is None:
                continue
            if (message in meta.message.lower()) or (likelyHash and message in meta.oid.hex):
                self.graphView.setCurrentIndex(modelIndex)
                return

        showInformation(self, self.tr("Find Commit"), self.tr("No more occurrences of “{0}”.").format(escape(message)))

    def findFlow(self):
        def onAccept(verbatimTerm):
            self.previouslySearchedTerm = verbatimTerm
            self._search(range(0, self.graphView.model().rowCount()))
        showTextInputDialog(
            self,
            self.tr("Find Commit"),
            self.tr("Search for partial commit hash or message:"),
            self.previouslySearchedTerm,
            onAccept)

    def _findNextOrPrevious(self, findNext):
        if not sanitizeSearchTerm(self.previouslySearchedTerm):
            showWarning(self, self.tr("Find Commit"), self.tr("Please use “Find” to specify a search term before using “Find Next” or “Find Previous”."))
            return
        if len(self.graphView.selectedIndexes()) == 0:
            showWarning(self, self.tr("Find Commit"), self.tr("Please select a commit from whence to resume the search."))
            return
        start = self.graphView.currentIndex().row()
        if findNext:
            self._search(range(1 + start, self.graphView.model().rowCount()))
        else:
            self._search(range(start - 1, -1, -1))

    def findNext(self):
        self._findNextOrPrevious(True)

    def findPrevious(self):
        self._findNextOrPrevious(False)

    # -------------------------------------------------------------------------
    # Find in diff, find next in diff

    def _searchDiff(self, forward=True):
        message = self.previouslySearchedTermInDiff
        message = sanitizeSearchTerm(message)
        if not message:
            showWarning(self, self.tr("Find in Diff"), self.tr("Invalid search term."))
            return

        doc: QTextDocument = self.diffView.document()
        newCursor = doc.find(message, self.diffView.textCursor())
        if newCursor:
            self.diffView.setTextCursor(newCursor)
            return

        showInformation(self, self.tr("Find in Diff"), self.tr("No more occurrences of “{0}”.").format(escape(message)))

    def findInDiffFlow(self):
        def onAccept(verbatimTerm):
            self.previouslySearchedTermInDiff = verbatimTerm
            self._searchDiff()
        showTextInputDialog(
            self,
            self.tr("Find in Diff"),
            self.tr("Search for text in current diff:"),
            self.previouslySearchedTermInDiff,
            onAccept)

    def _findInDiffNextOrPrevious(self, findNext):
        if not sanitizeSearchTerm(self.previouslySearchedTermInDiff):
            showWarning(
                self,
                self.tr("Find in Diff"),
                self.tr("Please use “Find in Diff” to specify a search term before using “Find Next” or “Find Previous”."))
            return
        self._searchInDiff(findNext)

    def findInDiffNext(self):
        self._findNextOrPrevious(True)

    def findInDiffPrevious(self):
        self._findNextOrPrevious(False)

    # -------------------------------------------------------------------------

    def toggleHideBranch(self, branchName: str):
        assert branchName.startswith("refs/")
        self.state.toggleHideBranch(branchName)
        self.graphView.setHiddenCommits(self.state.hiddenCommits)

    # -------------------------------------------------------------------------

    @property
    def isStageViewShown(self):
        return self.filesStack.currentWidget() == self.stageSplitter

    def quickRefresh(self):
        self.scheduledRefresh.stop()

        with Benchmark("Refresh refs-by-commit cache"):
            self.state.refreshRefsByCommitCache()

        with Benchmark("Load tainted commits only"):
            nRemovedRows, nAddedRows = self.state.loadTaintedCommitsOnly()

        with Benchmark(F"Refresh top of graphview ({nRemovedRows} removed, {nAddedRows} added)"):
            if nRemovedRows >= 0:
                self.graphView.refreshTopOfCommitSequence(nRemovedRows, nAddedRows, self.state.commitSequence)
            else:
                self.graphView.setCommitSequence(self.state.commitSequence)

        if self.isStageViewShown:
            self.fillStageViewAsync()
        globalstatus.clearProgress()

        self.refreshWindowTitle()

    def quickRefreshWithSidebar(self):
        self.quickRefresh()
        self.sidebar.refresh(self.state)

    def refreshWindowTitle(self):
        shortname = self.state.shortName
        repo = self.repo
        inBrackets = ""
        if repo.head_is_unborn:
            inBrackets = self.tr("unborn HEAD")
        elif repo.is_empty:  # getActiveBranchShorthand won't work on an empty repo
            inBrackets = self.tr("repo is empty")
        elif repo.head_is_detached:
            oid = porcelain.getHeadCommitOid(repo)
            inBrackets = self.tr("detached HEAD @ {0}").format(shortHash(oid))
        else:
            inBrackets = porcelain.getActiveBranchShorthand(repo)

        suffix = QApplication.applicationDisplayName()
        if settings.prefs.debug_showPID:
            suffix += F" (PID {os.getpid()}, {qtBindingName})"

        self.window().setWindowTitle(F"{shortname} [{inBrackets}] — {suffix}")

    # -------------------------------------------------------------------------

    def selectRef(self, refName: str):
        oid = porcelain.getCommitOidFromReferenceName(self.repo, refName)
        self.graphView.selectCommit(oid)

    """
    def selectTag(self, tagName: str):
        oid = porcelain.getCommitOidFromTagName(self.repo, tagName)
        self.selectCommit(oid)
    """

    # -------------------------------------------------------------------------

    def openRescueFolder(self):
        trash = Trash(self.repo)
        if trash.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(trash.trashDir))
        else:
            showInformation(
                self,
                self.tr("Open Rescue Folder"),
                self.tr("There’s no rescue folder for this repository. Perhaps you haven’t discarded a change with {0} yet.").format(QApplication.applicationDisplayName()))

    def clearRescueFolder(self):
        trash = Trash(self.repo)
        sizeOnDisk, patchCount = trash.getSize()

        if patchCount <= 0:
            showInformation(
                self,
                self.tr("Clear Rescue Folder"),
                self.tr("There are no discarded changes to delete."))
            return

        humanSize = self.locale().formattedDataSize(sizeOnDisk)

        askPrompt = (
            self.tr("Do you want to permanently delete <b>%n</b> discarded patch(es)?", "", patchCount) + "<br>" +
            self.tr("This will free up {0} on disk.").format(humanSize) + "<br>" +
            translate("Global", "This cannot be undone!"))

        askConfirmation(
            parent=self,
            title=self.tr("Clear rescue folder"),
            text=askPrompt,
            callback=lambda: trash.clear(),
            okButtonText=self.tr("Delete permanently"),
            okButtonIcon=stockIcon(QStyle.StandardPixmap.SP_DialogDiscardButton))
