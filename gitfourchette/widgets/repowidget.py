from gitfourchette import porcelain
from gitfourchette import settings
from gitfourchette.actionflows import ActionFlows
from gitfourchette.benchmark import Benchmark
from gitfourchette.globalstatus import globalstatus
from gitfourchette.navhistory import NavHistory, NavPos
from gitfourchette.qt import *
from gitfourchette.repostate import RepoState
from gitfourchette.stagingstate import StagingState
from gitfourchette.trash import Trash
from gitfourchette.util import (fplural, excMessageBox, excStrings, labelQuote, QSignalBlockerContext, shortHash)
from gitfourchette.widgets.brandeddialog import showTextInputDialog
from gitfourchette.widgets.diffmodel import DiffModel, DiffModelError
from gitfourchette.widgets.diffview import DiffView
from gitfourchette.widgets.filelist import FileList, DirtyFiles, StagedFiles, CommittedFiles, FileListModel
from gitfourchette.widgets.graphview import GraphView
from gitfourchette.widgets.remotelinkprogressdialog import RemoteLinkProgressDialog
from gitfourchette.widgets.richdiffview import RichDiffView
from gitfourchette.widgets.sidebar import Sidebar
from gitfourchette.workqueue import WorkQueue
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
    pathPending: str  # path of the repository if it isn't loaded yet (state=None)

    previouslySearchedTerm: str
    previouslySearchedTermInDiff: str

    navPos: NavPos
    navHistory: NavHistory

    @property
    def repo(self) -> pygit2.Repository:
        return self.state.repo

    @property
    def isLoaded(self):
        return self.state is not None

    def __init__(self, parent, sharedSplitterStates=None):
        super().__init__(parent)

        # Use workQueue to schedule operations on the repository
        # to run on a thread separate from the UI thread.
        self.workQueue = WorkQueue(self, maxThreadCount=1)

        self.state = None
        self.actionFlows = ActionFlows(None, self)

        self.pathPending = None

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

        # The staged files and unstaged files view are mutually exclusive.
        self.stagedFiles.entryClicked.connect(self.dirtyFiles.clearSelectionSilently)
        self.dirtyFiles.entryClicked.connect(self.stagedFiles.clearSelectionSilently)

        # Refresh file list views after applying a patch...
        self.diffView.patchApplied.connect(self.fillStageViewAsync)  # ...from the diff view (partial line patch);
        # Note that refreshing the file list views may, in turn, re-select a file from the appropriate file view,
        # which will trigger the diff view to be refreshed as well.

        self.stagedFiles.unstageFiles.connect(self.unstageFilesAsync)
        self.dirtyFiles.stageFiles.connect(self.stageFilesAsync)
        self.dirtyFiles.discardFiles.connect(self.actionFlows.discardFilesFlow)  # we need to confirm deletions

        for v in [self.dirtyFiles, self.stagedFiles, self.committedFiles]:
            v.nothingClicked.connect(self.diffView.clear)
            v.entryClicked.connect(self.loadPatchAsync)

        self.graphView.emptyClicked.connect(self.setNoCommitSelected)
        self.graphView.commitClicked.connect(self.loadCommitAsync)
        self.graphView.uncommittedChangesClicked.connect(self.fillStageViewAsync)
        self.graphView.resetHead.connect(self.resetHeadAsync)
        self.graphView.newBranchFromCommit.connect(self.newBranchFromCommitAsync)

        self.sidebar.commit.connect(self.startCommitFlow)
        self.sidebar.commitClicked.connect(self.graphView.selectCommit)
        self.sidebar.deleteBranch.connect(self.actionFlows.deleteBranchFlow)
        self.sidebar.deleteRemote.connect(self.actionFlows.deleteRemoteFlow)
        self.sidebar.editRemote.connect(self.actionFlows.editRemoteFlow)
        self.sidebar.editTrackingBranch.connect(self.actionFlows.editTrackingBranchFlow)
        self.sidebar.fetchRemote.connect(self.fetchRemoteAsync)
        self.sidebar.fetchRemoteBranch.connect(self.fetchRemoteBranchAsync)
        self.sidebar.pushBranch.connect(self.actionFlows.pushFlow)
        self.sidebar.newBranch.connect(self.actionFlows.newBranchFlow)
        self.sidebar.newRemote.connect(self.actionFlows.newRemoteFlow)
        self.sidebar.newTrackingBranch.connect(self.actionFlows.newTrackingBranchFlow)
        self.sidebar.refClicked.connect(self.selectRef)
        self.sidebar.renameBranch.connect(self.actionFlows.renameBranchFlow)
        self.sidebar.switchToBranch.connect(self.switchToBranchAsync)
        self.sidebar.uncommittedChangesClicked.connect(self.graphView.selectUncommittedChanges)

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
        flows.discardFiles.connect(self.discardFilesAsync)
        flows.editRemote.connect(self.editRemoteAsync)
        flows.editTrackingBranch.connect(self.editTrackingBranchAsync)
        flows.newBranch.connect(self.newBranchAsync)
        flows.newRemote.connect(self.newRemoteAsync)
        flows.newStash.connect(self.newStashAsync)
        flows.newTrackingBranch.connect(self.newTrackingBranchAsync)
        flows.renameBranch.connect(self.renameBranchAsync)
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
        self.commitButton = QPushButton("&Commit")
        self.commitButton.clicked.connect(self.startCommitFlow)
        self.amendButton = QPushButton("&Amend")
        self.amendButton.clicked.connect(self.actionFlows.amendFlow)
        commitButtonsContainer.layout().addWidget(self.commitButton)
        commitButtonsContainer.layout().addWidget(self.amendButton)
        self.stageSplitter = QSplitter(Qt.Vertical)
        self.stageSplitter.addWidget(dirtyContainer)
        self.stageSplitter.addWidget(stageContainer)

        self.filesStack.addWidget(self.committedFiles)
        self.filesStack.addWidget(self.stageSplitter)
        self.filesStack.setCurrentWidget(self.committedFiles)

        self.diffStack.addWidget(self.diffView)
        self.diffStack.addWidget(self.richDiffView)
        self.diffStack.setCurrentWidget(self.diffView)

        bottomSplitter = QSplitter(Qt.Horizontal)
        bottomSplitter.addWidget(self.filesStack)
        bottomSplitter.addWidget(self.diffStack)
        bottomSplitter.setSizes([100, 300])

        mainSplitter = QSplitter(Qt.Vertical)
        mainSplitter.addWidget(self.graphView)
        mainSplitter.addWidget(bottomSplitter)
        mainSplitter.setSizes([100, 150])

        sideSplitter = QSplitter(Qt.Horizontal)
        sideSplitter.addWidget(self.sidebar)
        sideSplitter.addWidget(mainSplitter)
        sideSplitter.setSizes([100, 500])

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
        #    w.setFrameStyle(QFrame.NoFrame)
        self.sidebar.setFrameStyle(QFrame.NoFrame)

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

    @property
    def workdir(self):
        if self.state:
            return os.path.normpath(self.state.repo.workdir)
        else:
            return self.pathPending

    def getTitle(self):
        if self.state:
            return self.state.shortName
        elif self.pathPending:
            return F"({settings.history.getRepoNickname(self.pathPending)})"
        else:
            return "???"

    def cleanup(self):
        if self.state and self.state.repo:
            self.committedFiles.clear()
            self.dirtyFiles.clear()
            self.stagedFiles.clear()
            self.graphView._replaceModel(None)
            self.diffView.clear()
            # Save path if we want to reload the repo later
            self.pathPending = os.path.normpath(self.state.repo.workdir)
            self.state.repo.free()
            self.state = None

    def setPendingWorkdir(self, path):
        self.pathPending = os.path.normpath(path)

    def startCommitFlow(self):
        initialMessage = self.state.getDraftCommitMessage()
        self.actionFlows.commitFlow(initialMessage)

    def renameRepo(self):
        def onAccept(newName):
            settings.history.setRepoNickname(self.workdir, newName)
            self.nameChange.emit()
        showTextInputDialog(
            self,
            "Edit repo nickname",
            "Enter new nickname for repo, or enter blank line to reset:",
            settings.history.getRepoNickname(self.workdir),
            onAccept,
            okButtonText="Rename")

    def setNoCommitSelected(self):
        self.saveFilePositions()
        self.navPos = NavPos()

        self.filesStack.setCurrentWidget(self.stageSplitter)
        self.committedFiles.clear()

    def fillStageViewAsync(self, forceSelectFile: NavPos = None):
        """Fill Staged/Unstaged views with uncommitted changes"""

        repo = self.state.repo

        def work() -> tuple[pygit2.Diff, pygit2.Diff]:
            dirtyDiff = porcelain.diffWorkdirToIndex(repo)
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
            self.dirtyLabel.setText(fplural(F"# dirty file^s:", nDirty))
            self.stageLabel.setText(fplural(F"# file^s staged for commit:", nStaged))

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
                self.diffView.clear()

            self.navHistory.unlock()

        stagedESR = self.stagedFiles.earliestSelectedRow()
        dirtyESR = self.dirtyFiles.earliestSelectedRow()

        self.saveFilePositions()
        self.workQueue.put(work, then, "Refreshing working tree status", -1000)

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

            # Switch to correct card in filesStack to show changedFilesView
            self.filesStack.setCurrentWidget(self.committedFiles)

            self.restoreSelectedFile()

        self.saveFilePositions()
        self.workQueue.put(work, then, F"Loading commit “{shortHash(oid)}”", -1000)

    def loadPatchAsync(self, patch: pygit2.Patch, stagingState: StagingState):
        """Load a file diff into the pygit2.Diff View"""

        if not patch:
            self.diffStack.setCurrentWidget(self.richDiffView)
            self.richDiffView.displayDiffModelError(DiffModelError(
                "Patch is invalid.",
                "The patched file may have changed on disk since we last read it. Try refreshing the window.",
                icon=QStyle.SP_MessageBoxWarning))
            return

        repo = self.state.repo

        def work():
            dm = None
            error = None
            try:
                dm = DiffModel.fromPatch(patch)
                dm.document.moveToThread(QApplication.instance().thread())
            except DiffModelError as dme:
                error = dme
            except BaseException as exc:
                summary, details = excStrings(exc)
                error = DiffModelError(summary, icon=QStyle.SP_MessageBoxCritical, preformatted=details)
            return dm, error

        def then(returned: tuple):
            dm: DiffModel
            error: DiffModelError
            dm, error = returned

            if stagingState == StagingState.COMMITTED:
                assert len(self.navPos.context) == 40
                posContext = self.navPos.context
            else:
                posContext = stagingState.name
            posFile = patch.delta.new_file.path
            self.navPos = self.navHistory.findFileInContext(posContext, posFile)
            if not self.navPos:
                self.navPos = NavPos(posContext, posFile)

            if error:
                self.diffStack.setCurrentWidget(self.richDiffView)
                self.richDiffView.displayDiffModelError(error)
            else:
                self.diffStack.setCurrentWidget(self.diffView)
                self.diffView.replaceDocument(repo, patch, stagingState, dm)
                self.restoreDiffPosition()  # restore position after we've replaced the document

        self.saveFilePositions()
        self.workQueue.put(work, then, F"Loading diff “{patch.delta.new_file.path}”", -500)

    def createCommitAsync(self, message: str, author: pygit2.Signature | None, committer: pygit2.Signature | None):
        def work():
            porcelain.createCommit(self.repo, message, author, committer)

        def then(_):
            self.state.setDraftCommitMessage(None)  # Clear draft message
            self.quickRefreshWithSidebar()

        # Save commit message as draft now, so we don't lose it if the commit fails.
        self.state.setDraftCommitMessage(message)
        self.workQueue.put(work, then, F"Committing")

    def amendCommitAsync(self, message: str, author: pygit2.Signature | None, committer: pygit2.Signature | None):
        def work():
            porcelain.amendCommit(self.repo, message, author, committer)

        def then(_):
            self.quickRefreshWithSidebar()

        self.workQueue.put(work, then, F"Amending")

    def switchToBranchAsync(self, newBranch: str):
        assert not newBranch.startswith("refs/heads/")
        work = lambda: porcelain.checkoutLocalBranch(self.repo, newBranch)
        then = lambda _: self.quickRefreshWithSidebar()
        self.workQueue.put(work, then, F"Switching to branch “{newBranch}”")

    def renameBranchAsync(self, oldName: str, newName: str):
        assert not oldName.startswith("refs/heads/")
        work = lambda: porcelain.renameBranch(self.repo, oldName, newName)
        then = lambda _: self.quickRefreshWithSidebar()
        self.workQueue.put(work, then, F"Renaming branch “{oldName}” to “{newName}”")

    def deleteBranchAsync(self, localBranchName: str):
        assert not localBranchName.startswith("refs/heads/")
        work = lambda: porcelain.deleteBranch(self.repo, localBranchName)
        then = lambda _: self.quickRefreshWithSidebar()
        self.workQueue.put(work, then, F"Deleting branch “{localBranchName}”")

    def newBranchAsync(self, localBranchName: str):
        assert not localBranchName.startswith("refs/heads/")
        work = lambda: porcelain.newBranch(self.repo, localBranchName)
        then = lambda _: self.quickRefreshWithSidebar()
        self.workQueue.put(work, then, F"Creating branch “{localBranchName}”")

    def newTrackingBranchAsync(self, localBranchName: str, remoteBranchName: str):
        assert not localBranchName.startswith("refs/heads/")
        work = lambda: porcelain.newTrackingBranch(self.repo, localBranchName, remoteBranchName)
        then = lambda _: self.quickRefreshWithSidebar()
        self.workQueue.put(work, then, F"Setting up branch “{localBranchName}” to track “{remoteBranchName}”")

    def newBranchFromCommitAsync(self, localBranchName: str, commitOid: pygit2.Oid):
        work = lambda: porcelain.newBranchFromCommit(self.repo, localBranchName, commitOid)
        then = lambda _: self.quickRefreshWithSidebar()
        self.workQueue.put(work, then, F"Creating branch “{localBranchName}” from commit “{shortHash(commitOid)}”")

    def editTrackingBranchAsync(self, localBranchName: str, remoteBranchName: str):
        work = lambda: porcelain.editTrackingBranch(self.repo, localBranchName, remoteBranchName)
        then = lambda _: self.quickRefreshWithSidebar()
        self.workQueue.put(work, then, F"Making local branch “{localBranchName}” track “{remoteBranchName}”")

    def newRemoteAsync(self, name: str, url: str):
        work = lambda: porcelain.newRemote(self.repo, name, url)
        then = lambda _: self.quickRefreshWithSidebar()
        self.workQueue.put(work, then, F"New remote “{name}”")

    def editRemoteAsync(self, remoteName: str, newName: str, newURL: str):
        work = lambda: porcelain.editRemote(self.repo, remoteName, newName, newURL)
        then = lambda _: self.quickRefreshWithSidebar()
        self.workQueue.put(work, then, F"Edit remote “{remoteName}”")

    def fetchRemoteAsync(self, remoteName: str):
        rlpd = RemoteLinkProgressDialog(self)

        def work():
            return porcelain.fetchRemote(self.repo, remoteName, rlpd.remoteLink)

        def then(_):
            rlpd.close()
            self.quickRefreshWithSidebar()

        def onError(exc):
            rlpd.close()
            excMessageBox(exc, title="Fetch error", message=F"Couldn't fetch “{remoteName}”.", parent=self)

        self.workQueue.put(work, then, F"Fetch remote “{remoteName}”", errorCallback=onError)

    def fetchRemoteBranchAsync(self, remoteBranchName: str):
        rlpd = RemoteLinkProgressDialog(self)

        def work():
            return porcelain.fetchRemoteBranch(self.repo, remoteBranchName, rlpd.remoteLink)

        def then(_):
            rlpd.close()
            self.quickRefreshWithSidebar()

        def onError(exc):
            rlpd.close()
            excMessageBox(exc, title="Fetch error", message=F"Couldn't fetch remote branch “{remoteBranchName}”.", parent=self)

        self.workQueue.put(work, then, F"Fetch remote branch “{remoteBranchName}”", errorCallback=onError)

    def deleteRemoteAsync(self, remoteName: str):
        work = lambda: porcelain.deleteRemote(self.repo, remoteName)
        then = lambda _: self.quickRefreshWithSidebar()
        self.workQueue.put(work, then, F"Deleting remote “{remoteName}”")

    def resetHeadAsync(self, onto: pygit2.Oid, resetMode: str, recurseSubmodules: bool):
        work = lambda: porcelain.resetHead(self.repo, onto, resetMode, recurseSubmodules)
        def then(_):
            self.quickRefreshWithSidebar()
            self.graphView.selectCommit(onto)
        self.workQueue.put(work, then, F"Reset HEAD onto {shortHash(onto)}, {resetMode}")

    def stageFilesAsync(self, patches: list[pygit2.Patch]):
        work = lambda: porcelain.stageFiles(self.repo, patches)
        then = lambda _: self.quickRefreshWithSidebar()
        self.workQueue.put(work, then, fplural("Staging # file^s", len(patches)))

    def discardFilesAsync(self, patches: list[pygit2.Patch]):
        def work():
            paths = [patch.delta.new_file.path for patch in patches]
            Trash(self.repo).backupPatches(patches)
            porcelain.discardFiles(self.repo, paths)
        then = lambda _: self.quickRefreshWithSidebar()
        self.workQueue.put(work, then, fplural("Discarding # file^s", len(patches)))

    def unstageFilesAsync(self, patches: list[pygit2.Patch]):
        work = lambda: porcelain.unstageFiles(self.repo, patches)
        then = lambda _: self.quickRefreshWithSidebar()
        self.workQueue.put(work, then, fplural("Unstaging # file^s", len(patches)))

    def newStashAsync(self, message: str, flags: str):
        def work(): return porcelain.newStash(self.repo, message, flags)
        then = lambda _: self.quickRefreshWithSidebar()
        self.workQueue.put(work, then, "New stash")

    def applyStashAsync(self, commitId: pygit2.Oid):
        def work(): porcelain.applyStash(self.repo, commitId)
        then = lambda _: self.quickRefreshWithSidebar()
        self.workQueue.put(work, then, "Apply stash")

    def popStashAsync(self, commitId: pygit2.Oid):
        def work(): porcelain.popStash(self.repo, commitId)
        then = lambda _: self.quickRefreshWithSidebar()
        self.workQueue.put(work, then, "Pop stash")

    def dropStashAsync(self, commitId: pygit2.Oid):
        def work(): porcelain.dropStash(self.repo, commitId)
        then = lambda _: self.quickRefreshWithSidebar()
        self.workQueue.put(work, then, "Delete stash")

    def openSubmoduleRepo(self, submoduleKey: str):
        path = porcelain.getSubmoduleWorkdir(self.repo, submoduleKey)
        self.window().openRepo(path)

    def openSubmoduleFolder(self, submoduleKey: str):
        path = porcelain.getSubmoduleWorkdir(self.repo, submoduleKey)
        url = QUrl.fromLocalFile(path)
        QDesktopServices.openUrl(url)

    # -------------------------------------------------------------------------
    # Pull
    # (WIP)

    def pull(self):
        repo = self.state.repo
        branch = repo.active_branch
        tracking = repo.active_branch.tracking_branch()
        remote = repo.remote(tracking.remote_name)
        remote.fetch()

    # -------------------------------------------------------------------------
    # Find, find next

    def _search(self, searchRange):
        message = self.previouslySearchedTerm
        message = sanitizeSearchTerm(message)
        if not message:
            QMessageBox.warning(self, "Find Commit", "Invalid search term.")
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

        QMessageBox.information(self, "Find Commit", F"No more occurrences of “{message}”.")

    def findFlow(self):
        def onAccept(verbatimTerm):
            self.previouslySearchedTerm = verbatimTerm
            self._search(range(0, self.graphView.model().rowCount()))
        showTextInputDialog(
            self,
            "Find commit",
            "Search for partial commit hash or message:",
            self.previouslySearchedTerm,
            onAccept)

    def _findNextOrPrevious(self, findNext):
        if not sanitizeSearchTerm(self.previouslySearchedTerm):
            QMessageBox.warning(self, "Find Commit", "Please use “Find” to specify a search term before using “Find Next” or “Find Previous”.")
            return
        if len(self.graphView.selectedIndexes()) == 0:
            QMessageBox.warning(self, "Find Commit", "Please select a commit from whence to resume the search.")
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
            QMessageBox.warning(self, "Find in pygit2.Patch", "Invalid search term.")
            return

        doc: QTextDocument = self.diffView.document()
        newCursor = doc.find(message, self.diffView.textCursor())
        if newCursor:
            self.diffView.setTextCursor(newCursor)
            return

        QMessageBox.information(self, "Find in pygit2.Patch", F"No more occurrences of “{message}”.")

    def findInDiffFlow(self):
        def onAccept(verbatimTerm):
            self.previouslySearchedTermInDiff = verbatimTerm
            self._searchDiff()
        showTextInputDialog(
            self,
            "Find in patch",
            "Search for text in current patch:",
            self.previouslySearchedTermInDiff,
            onAccept)

    def _findInDiffNextOrPrevious(self, findNext):
        if not sanitizeSearchTerm(self.previouslySearchedTermInDiff):
            QMessageBox.warning(self, "Find in pygit2.Patch", "Please use “Find in Patch” to specify a search term before using “Find Next” or “Find Previous”.")
            return
        #if len(self.graphView.selectedIndexes()) == 0:
        #    QMessageBox.warning(self, "Find in pygit2.Patch", "Please select a commit from whence to resume the search.")
        #    return
        self._searchInDiff(findNext)

    def findInDiffNext(self):
        self._findNextOrPrevious(True)

    def findInDiffPrevious(self):
        self._findNextOrPrevious(False)

    # -------------------------------------------------------------------------

    def quickRefresh(self):
        with Benchmark("Load tainted commits only"):
            nRemovedRows, nAddedRows = self.state.loadTaintedCommitsOnly()

        with Benchmark(F"Refresh top of graphview ({nRemovedRows} removed, {nAddedRows} added)"):
            if nRemovedRows >= 0:
                self.graphView.refreshTopOfCommitSequence(nRemovedRows, nAddedRows, self.state.commitSequence)
            else:
                self.graphView.setCommitSequence(self.state.commitSequence)

        with Benchmark("Refresh refs-by-commit cache"):
            self.state.refreshRefsByCommitCache()

        if self.filesStack.currentWidget() == self.stageSplitter:
            self.fillStageViewAsync()
        globalstatus.clearProgress()

        self.refreshWindowTitle()

    def quickRefreshWithSidebar(self):
        self.quickRefresh()
        self.sidebar.fill(self.repo)

    def refreshWindowTitle(self):
        shortname = self.state.shortName
        repo = self.repo
        inBrackets = ""
        if repo.head_is_unborn:
            inBrackets = F"unborn HEAD"
        elif repo.is_empty:  # getActiveBranchShorthand won't work on an empty repo
            inBrackets = "repo is empty"
        elif repo.head_is_detached:
            oid = porcelain.getHeadCommitOid(repo)
            inBrackets = F"detached HEAD @ {shortHash(oid)}"
        else:
            inBrackets = porcelain.getActiveBranchShorthand(repo)
        self.window().setWindowTitle(F"{shortname} [{inBrackets}] — {QApplication.applicationDisplayName()}")

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
        trash = Trash(self.state.repo)
        if trash.exists():
            QDesktopServices.openUrl(trash.trashDir)
        else:
            QMessageBox.information(
                self,
                "Open Rescue Folder",
                "There’s no rescue folder for this repository. Perhaps you haven’t "
                F"discarded a change with {QApplication.applicationDisplayName()} yet.")

    def clearRescueFolder(self):
        trash = Trash(self.state.repo)
        sizeOnDisk, patchCount = trash.getSize()

        if patchCount <= 0:
            QMessageBox.information(self, "Clear Rescue Folder", "There are no discarded changes to delete.")
            return

        humanSize = self.locale().formattedDataSize(sizeOnDisk)
        result = QMessageBox.question(
            self,
            "Clear Rescue Folder",
            F"Do you want to permanently delete {fplural('# discarded patch^es', patchCount)}?\n"
            F"This will free up {humanSize} on disk.\n"
            F"This cannot be undone!")

        if result == QMessageBox.Yes:
            trash.clear()
