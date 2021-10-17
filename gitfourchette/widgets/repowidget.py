import trash
from allqt import *
from allgit import *
from benchmark import Benchmark
from dialogs.commitdialog import CommitDialog
from dialogs.remoteprogressdialog import RemoteProgressDialog
from diffmodel import DiffModel
from stagingstate import StagingState
from globalstatus import globalstatus
from repostate import RepoState
from typing import Callable
from util import fplural, excMessageBox, excStrings, labelQuote, textInputDialog, QSignalBlockerContext, shortHash
from widgets.diffview import DiffView
from widgets.dirtyfilelistview import DirtyFileListView
from widgets.filelistview import FileListView
from widgets.graphview import GraphView
from widgets.sidebar import Sidebar
from widgets.stagedfilelistview import StagedFileListView
from workqueue import WorkQueue
import os
import porcelain
import pygit2
import settings
import typing


FILESSTACK_READONLY_CARD = 0
FILESSTACK_STAGE_CARD = 1


def sanitizeSearchTerm(x):
    if not x:
        return None
    return x.strip().lower()


def unimplementedDialog(featureName="UNIMPLEMENTED"):
    QMessageBox.warning(None, featureName, F"This feature isn't implemented yet\n({featureName})")


class RepoWidget(QWidget):
    nameChange: Signal = Signal()

    state: RepoState
    pathPending: str  # path of the repository if it isn't loaded yet (state=None)

    previouslySearchedTerm: str
    previouslySearchedTermInDiff: str

    displayedCommitOid: Oid
    displayedFilePath: str
    displayedStagingState: StagingState
    # TODO: refactor this
    latestStagedOrUnstaged: StagingState
    fileListSelectedRowCache: dict[typing.Union[str, StagingState], int]
    diffViewScrollPositionCache: dict[tuple[typing.Union[str, StagingState], str], int]
    diffViewCursorPositionCache: dict[tuple[typing.Union[str, StagingState], str], int]

    @property
    def repo(self) -> Repository:
        return self.state.repo

    def __init__(self, parent, sharedSplitterStates=None):
        super().__init__(parent)

        # Use workQueue to schedule operations on the repository
        # to run on a thread separate from the UI thread.
        self.workQueue = WorkQueue(self, maxThreadCount=1)

        self.state = None
        self.pathPending = None

        self.displayedCommitOid = None
        self.displayedFilePath = None
        self.displayedStagingState = None
        self.fileListSelectedRowCache = {}
        self.diffViewScrollPositionCache = {}
        self.diffViewCursorPositionCache = {}
        self.latestStagedOrUnstaged = None

        self.graphView = GraphView(self)
        self.filesStack = QStackedWidget()
        self.diffView = DiffView(self)
        self.changedFilesView = FileListView(self, StagingState.COMMITTED)
        self.dirtyView = DirtyFileListView(self)
        self.stageView = StagedFileListView(self)
        self.sidebar = Sidebar(self)

        # The staged files and unstaged files view are mutually exclusive.
        self.stageView.entryClicked.connect(self.dirtyView.clearSelectionSilently)
        self.dirtyView.entryClicked.connect(self.stageView.clearSelectionSilently)

        # Refresh file list views after applying a patch...
        self.diffView.patchApplied.connect(self.fillStageViewAsync)  # ...from the diff view (partial line patch);
        self.stageView.patchApplied.connect(self.fillStageViewAsync)  # ...from the staged file view (unstage entire file);
        self.dirtyView.patchApplied.connect(self.fillStageViewAsync)  # ...and from the dirty file view (stage entire file).
        # Note that refreshing the file list views may, in turn, re-select a file from the appropriate file view,
        # which will trigger the diff view to be refreshed as well.

        for v in [self.dirtyView, self.stageView, self.changedFilesView]:
            v.nothingClicked.connect(self.diffView.clear)
            v.entryClicked.connect(self.loadPatchAsync)

        self.graphView.emptyClicked.connect(self.setNoCommitSelected)
        self.graphView.commitClicked.connect(self.loadCommitAsync)
        self.graphView.uncommittedChangesClicked.connect(self.fillStageViewAsync)
        self.graphView.resetHead.connect(self.resetHeadAsync)
        self.graphView.newBranchFromCommit.connect(self.newBranchFromCommitAsync)

        self.sidebar.uncommittedChangesClicked.connect(self.graphView.selectUncommittedChanges)
        self.sidebar.refClicked.connect(self.selectRef)
        self.sidebar.tagClicked.connect(self.selectTag)
        self.sidebar.newBranch.connect(self.newBranchAsync)
        self.sidebar.switchToBranch.connect(self.switchToBranchAsync)
        self.sidebar.renameBranch.connect(self.renameBranchAsync)
        self.sidebar.editTrackingBranch.connect(self.editTrackingBranchAsync)
        self.sidebar.mergeBranchIntoActive.connect(lambda name: unimplementedDialog("Merge Other Branch Into Active Branch"))
        self.sidebar.rebaseActiveOntoBranch.connect(lambda name: unimplementedDialog("Rebase Active Branch Into Other Branch"))
        self.sidebar.deleteBranch.connect(self.deleteBranchAsync)
        self.sidebar.newTrackingBranch.connect(self.newTrackingBranchAsync)
        self.sidebar.editRemoteURL.connect(self.editRemoteURLAsync)
        self.sidebar.pushBranch.connect(lambda name: self.push(name))

        self.splitterStates = sharedSplitterStates or {}

        self.dirtyLabel = QLabel("Dirty Files")
        self.stageLabel = QLabel("Files Staged For Commit")

        self.previouslySearchedTerm = None
        self.previouslySearchedTermInDiff = None

        dirtyContainer = QWidget()
        dirtyContainer.setLayout(QVBoxLayout())
        dirtyContainer.layout().setContentsMargins(0, 0, 0, 0)
        dirtyContainer.layout().addWidget(self.dirtyLabel)
        dirtyContainer.layout().addWidget(self.dirtyView)
        stageContainer = QWidget()
        stageContainer.setLayout(QVBoxLayout())
        stageContainer.layout().setContentsMargins(0, 0, 0, 0)
        stageContainer.layout().addWidget(self.stageLabel)
        stageContainer.layout().addWidget(self.stageView)
        commitButtonsContainer = QWidget()
        commitButtonsContainer.setLayout(QHBoxLayout())
        commitButtonsContainer.layout().setContentsMargins(0, 0, 0, 0)
        stageContainer.layout().addWidget(commitButtonsContainer)
        commitButton = QPushButton("&Commit")
        commitButton.clicked.connect(self.commitFlow)
        commitButtonsContainer.layout().addWidget(commitButton)
        amendButton = QPushButton("&Amend")
        amendButton.clicked.connect(self.amendFlow)
        commitButtonsContainer.layout().addWidget(amendButton)
        stageSplitter = QSplitter(Qt.Vertical)
        stageSplitter.setHandleWidth(settings.prefs.splitterHandleWidth)
        stageSplitter.addWidget(dirtyContainer)
        stageSplitter.addWidget(stageContainer)

        assert FILESSTACK_READONLY_CARD == self.filesStack.count()
        self.filesStack.addWidget(self.changedFilesView)
        assert FILESSTACK_STAGE_CARD == self.filesStack.count()
        self.filesStack.addWidget(stageSplitter)
        self.filesStack.setCurrentIndex(FILESSTACK_READONLY_CARD)

        bottomSplitter = QSplitter(Qt.Horizontal)
        bottomSplitter.setHandleWidth(settings.prefs.splitterHandleWidth)
        bottomSplitter.addWidget(self.filesStack)
        bottomSplitter.addWidget(self.diffView)
        bottomSplitter.setSizes([100, 300])

        mainSplitter = QSplitter(Qt.Vertical)
        mainSplitter.setHandleWidth(settings.prefs.splitterHandleWidth)
        mainSplitter.addWidget(self.graphView)
        mainSplitter.addWidget(bottomSplitter)
        mainSplitter.setSizes([100, 150])

        sideSplitter = QSplitter(Qt.Horizontal)
        sideSplitter.setHandleWidth(settings.prefs.splitterHandleWidth)
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
        stageSplitter.setObjectName("StageSplitter")
        sideSplitter.setObjectName("SideSplitter")
        self.splittersToSave = [mainSplitter, bottomSplitter, stageSplitter, sideSplitter]
        # save splitter state in splitterMoved signal
        for splitter in self.splittersToSave:
            splitter.splitterMoved.connect(lambda pos, index, splitter=splitter: self.saveSplitterState(splitter))

        # remove frames for a cleaner look
        for w in self.graphView, self.diffView, self.dirtyView, self.stageView, self.changedFilesView, self.sidebar:
            w.setFrameStyle(QFrame.NoFrame)

    def saveSplitterState(self, splitter: QSplitter):
        self.splitterStates[splitter.objectName()] = splitter.saveState()

    def restoreSplitterStates(self):
        for splitter in self.splittersToSave:
            try:
                splitter.restoreState(self.splitterStates[splitter.objectName()])
                splitter.setHandleWidth(settings.prefs.splitterHandleWidth)
            except KeyError:
                pass

    # -------------------------------------------------------------------------

    def getFileListAndCacheKey(self):
        if not self.displayedStagingState:
            return None, None

        elif self.displayedStagingState == StagingState.COMMITTED:
            fileListWidget = self.changedFilesView
            cacheKey = self.displayedCommitOid

        elif self.displayedStagingState.isDirty():
            fileListWidget = self.dirtyView
            cacheKey = self.displayedStagingState

        elif self.displayedStagingState == StagingState.STAGED:
            fileListWidget = self.stageView
            cacheKey = self.displayedStagingState

        else:
            return None, None

        return fileListWidget, cacheKey

    def saveFilePositions(self):
        fileListWidget, cacheKey = self.getFileListAndCacheKey()
        if not fileListWidget:
            return
        self.fileListSelectedRowCache[cacheKey] = fileListWidget.latestSelectedRow()
        self.diffViewScrollPositionCache[(cacheKey, self.displayedFilePath)] = self.diffView.verticalScrollBar().value()
        self.diffViewCursorPositionCache[(cacheKey, self.displayedFilePath)] = self.diffView.textCursor().position()
        if self.displayedStagingState != StagingState.COMMITTED:
            self.latestStagedOrUnstaged = self.displayedStagingState

    def restoreSelectedFile(self):
        fileListWidget, cacheKey = self.getFileListAndCacheKey()

        if not fileListWidget:
            return

        try:
            selectedRow = self.fileListSelectedRowCache[cacheKey]
        except KeyError:
            selectedRow = 0

        fileListWidget.selectRow(selectedRow)

    def restoreDiffViewPosition(self):
        fileListWidget, cacheKey = self.getFileListAndCacheKey()

        try:
            cursorPosition = self.diffViewCursorPositionCache[(cacheKey, self.displayedFilePath)]
            scrollPosition = self.diffViewScrollPositionCache[(cacheKey, self.displayedFilePath)]
        except KeyError:
            cursorPosition = 0
            scrollPosition = 0

        if cursorPosition > 0:
            newTextCursor = QTextCursor(self.diffView.textCursor())
            newTextCursor.setPosition(cursorPosition)
            self.diffView.setTextCursor(newTextCursor)

        self.diffView.verticalScrollBar().setValue(scrollPosition)

    # -------------------------------------------------------------------------

    @property
    def workingTreeDir(self):
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
            self.changedFilesView._setBlankModel()
            self.dirtyView._setBlankModel()
            self.stageView._setBlankModel()
            self.graphView._replaceModel(None)
            self.diffView.clear()
            # Save path if we want to reload the repo later
            self.pathPending = os.path.normpath(self.state.repo.workdir)
            self.state.repo.close()
            self.state = None

    def setPendingPath(self, path):
        self.pathPending = os.path.normpath(path)

    def renameRepo(self):
        text, ok = textInputDialog(
            self,
            "Edit Repo Nickname",
            "Enter new nickname for repo, or enter blank line to reset:",
            settings.history.getRepoNickname(self.workingTreeDir),
            okButtonText="Rename")
        if ok:
            settings.history.setRepoNickname(self.workingTreeDir, text)
            self.nameChange.emit()

    def setNoCommitSelected(self):
        self.saveFilePositions()
        self.filesStack.setCurrentIndex(FILESSTACK_STAGE_CARD)
        self.changedFilesView.clear()

    def fillStageViewAsync(self):
        """Fill Staged/Unstaged views with uncommitted changes"""

        repo = self.state.repo

        def work() -> tuple[Diff, Diff]:
            dirtyDiff = porcelain.loadDirtyDiff(repo)
            stageDiff = porcelain.loadStagedDiff(repo)
            return dirtyDiff, stageDiff

        def then(result: tuple[Diff, Diff]):
            dirtyDiff, stageDiff = result

            # Reset dirty & stage views. Block their signals as we refill them to prevent updating the diff view.
            with QSignalBlockerContext(self.dirtyView), QSignalBlockerContext(self.stageView):
                self.dirtyView.clear()
                self.stageView.clear()
                self.dirtyView.addFileEntriesFromDiff(dirtyDiff)
                self.stageView.addFileEntriesFromDiff(stageDiff)

            nDirty = self.dirtyView.model().rowCount()
            nStaged = self.stageView.model().rowCount()
            self.dirtyLabel.setText(fplural(F"# dirty file^s:", nDirty))
            self.stageLabel.setText(fplural(F"# file^s staged for commit:", nStaged))

            # Switch to correct card in filesStack to show dirtyView and stageView
            self.filesStack.setCurrentIndex(FILESSTACK_STAGE_CARD)

            # After patchApplied.emit has caused a refresh of the dirty/staged file views,
            # restore selected row in appropriate file list view so the user can keep hitting
            # enter (del) to stage (unstage) a series of files.
            if self.latestStagedOrUnstaged is not None:
                self.displayedStagingState = self.latestStagedOrUnstaged
            self.displayedFilePath = None
            self.restoreSelectedFile()

            # If no file is selected in either FileListView, clear the diffView of any residual diff.
            if 0 == (len(self.dirtyView.selectedIndexes()) + len(self.stageView.selectedIndexes())):
                self.diffView.clear()

        self.saveFilePositions()
        self.workQueue.put(work, then, "Refreshing index", -1000)

    def loadCommitAsync(self, oid: Oid):
        """Load commit details into Changed Files view"""

        work = lambda: porcelain.loadCommitDiffs(self.repo, oid)

        def then(parentDiffs: list[Diff]):
            #import time; time.sleep(1) #to debug out-of-order events

            # Reset changed files view. Block its signals as we refill it to prevent updating the diff view.
            with QSignalBlockerContext(self.changedFilesView):
                self.changedFilesView.clear()
                for diff in parentDiffs:
                    self.changedFilesView.addFileEntriesFromDiff(diff)

            self.displayedCommitOid = oid
            self.displayedStagingState = StagingState.COMMITTED

            # Click on the first file in the commit.
            # This will in turn fill the diff view.
            #self.changedFilesView.selectFirstRow()

            # Switch to correct card in filesStack to show changedFilesView
            self.filesStack.setCurrentIndex(FILESSTACK_READONLY_CARD)

            self.restoreSelectedFile()

        self.saveFilePositions()
        self.workQueue.put(work, then, F"Loading commit “{shortHash(oid)}”", -1000)

    def loadPatchAsync(self, patch: Patch, stagingState: StagingState):
        """Load a file diff into the Diff View"""

        repo = self.state.repo

        def work():
            try:
                if patch is not None:
                    allowRawFileAccess = stagingState.allowsRawFileAccess()
                    dm = DiffModel.fromPatch(repo, patch, allowRawFileAccess)
            except BaseException as exc:
                summary, details = excStrings(exc)
                dm = DiffModel.fromFailureMessage(summary, details)
            dm.document.moveToThread(QApplication.instance().thread())
            return dm

        def then(dm: DiffModel):
            self.displayedFilePath = patch.delta.new_file.path
            self.displayedStagingState = stagingState
            self.diffView.replaceDocument(repo, patch, stagingState, dm)
            self.restoreDiffViewPosition()  # restore position after we've replaced the document

        self.saveFilePositions()
        self.workQueue.put(work, then, F"Loading diff “{patch.delta.new_file.path}”", -500)

    def switchToBranchAsync(self, newBranch: str):
        work = lambda: porcelain.switchToBranch(self.repo, newBranch)
        then = lambda _: self.quickRefreshWithSidebar()
        self.workQueue.put(work, then, F"Switching to branch “{newBranch}”")

    def renameBranchAsync(self, oldName: str, newName: str):
        work = lambda: porcelain.renameBranch(self.repo, oldName, newName)
        then = lambda _: self.quickRefreshWithSidebar()
        self.workQueue.put(work, then, F"Renaming branch “{oldName}” to “{newName}”")

    def deleteBranchAsync(self, localBranchName: str):
        work = lambda: porcelain.deleteBranch(self.repo, localBranchName)
        then = lambda _: self.quickRefreshWithSidebar()
        self.workQueue.put(work, then, F"Deleting branch “{localBranchName}”")

    def newBranchAsync(self, localBranchName: str):
        work = lambda: porcelain.newBranch(self.repo, localBranchName)
        then = lambda _: self.quickRefreshWithSidebar()
        self.workQueue.put(work, then, F"Creating branch “{localBranchName}”")

    def newTrackingBranchAsync(self, localBranchName: str, remoteBranchName: str):
        work = lambda: porcelain.newTrackingBranch(self.repo, localBranchName, remoteBranchName)
        then = lambda _: self.quickRefreshWithSidebar()
        self.workQueue.put(work, then, F"Setting up branch “{localBranchName}” to track “{remoteBranchName}”")

    def newBranchFromCommitAsync(self, localBranchName: str, commitHexsha: str):
        work = lambda: porcelain.newBranchFromCommit(self.repo, localBranchName, commitHexsha)
        then = lambda _: self.quickRefreshWithSidebar()
        self.workQueue.put(work, then, F"Creating branch “{localBranchName}” from commit “{shortHash(commitHexsha)}”")

    def editTrackingBranchAsync(self, localBranchName: str, remoteBranchName: str):
        work = lambda: porcelain.editTrackingBranch(self.repo, localBranchName, remoteBranchName)
        then = lambda _: self.quickRefreshWithSidebar()
        self.workQueue.put(work, then, F"Making local branch “{localBranchName}” track “{remoteBranchName}”")

    def editRemoteURLAsync(self, remoteName: str, newURL: str):
        work = lambda: porcelain.editRemoteURL(self.repo, remoteName, newURL)
        then = lambda _: self.quickRefreshWithSidebar()
        self.workQueue.put(work, then, F"Edit remote “{remoteName}” URL")

    def resetHeadAsync(self, ontoHexsha: str, resetMode: str, recurseSubmodules: bool):
        work = lambda: porcelain.resetHead(self.repo, ontoHexsha, resetMode, recurseSubmodules)
        def then(_):
            self.quickRefreshWithSidebar()
            self.graphView.selectCommit(ontoHexsha)
        self.workQueue.put(work, then, F"Reset HEAD onto {shortHash(ontoHexsha)}, {resetMode}")

    # -------------------------------------------------------------------------
    # Push
    # TODO: make async!

    def push(self, branchName: str = None):
        repo = self.state.repo

        if not branchName:
            branchName = repo.active_branch.name

        branch = repo.heads[branchName]
        tracking = branch.tracking_branch()

        if not tracking:
            QMessageBox.warning(
                self,
                "Cannot Push a Non-Remote-Tracking Branch",
                F"""Can’t push local branch <b>{labelQuote(branch.name)}</b>
                because it isn’t tracking any remote branch.
                <br><br>To set a remote branch to track, right-click on
                local branch {labelQuote(branch.name)} in the sidebar,
                and pick “Tracking”.""")
            return

        remote = repo.remote(tracking.remote_name)
        urls = list(remote.urls)

        qmb = QMessageBox(self)
        qmb.setWindowTitle(F"Push “{branchName}”")
        qmb.setIcon(QMessageBox.Question)
        qmb.setText(F"""Confirm Push?<br>
            <br>Branch: <b>“{branch.name}”</b>
            <br>Tracking: <b>“{tracking.name}”</b>
            <br>Will be pushed to remote: <b>{'; '.join(urls)}</b>""")
        qmb.addButton("Push", QMessageBox.AcceptRole)
        qmb.addButton("Cancel", QMessageBox.RejectRole)
        if qmb.exec_() != QMessageBox.AcceptRole:
            return

        progress = RemoteProgressDialog(self, "Push in progress")
        pushInfos: list[git.PushInfo]

        PUSHINFO_FAILFLAGS = git.PushInfo.REJECTED | git.PushInfo.REMOTE_FAILURE | git.PushInfo.ERROR

        try:
            pushInfos = remote.put(refspec=branchName, progress=progress)
        except BaseException as e:
            progress.close()
            excMessageBox(e, "Push", "An error occurred while pushing.", parent=self)
            return

        progress.close()

        if len(pushInfos) == 0:
            QMessageBox.critical(self, "Push", "The push operation failed without a result.")
            return

        failed = False
        report = ""
        for info in pushInfos:
            if 0 != (info.flags & PUSHINFO_FAILFLAGS):
                failed = True
            report += F"{info.remote_ref_string}: {info.summary.strip()}\n"
            print(F"push info: {info}, summary: {info.summary.strip()}, local ref: {info.local_ref}; remote ref: {info.remote_ref_string}")

        report = report.rstrip()
        if failed:
            report = "Push failed.\n\n" + report
            QMessageBox.warning(self, "Push failed", report)
        else:
            self.quickRefresh()
            report = "Push successful!\n\n" + report
            QMessageBox.information(self, "Push successful", report)

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
    # Commit, amend

    def commitFlow(self):
        if not porcelain.hasAnyStagedChanges(self.repo):
            qmb = QMessageBox(self)
            qmb.setIcon(QMessageBox.Question)
            qmb.setWindowTitle("Empty Commit")
            qmb.setText("No files are staged for commit.\nDo you want to create an empty commit anyway?")
            ok = qmb.addButton("Go back", QMessageBox.AcceptRole)
            emptyCommit = qmb.addButton("Create empty commit", QMessageBox.ActionRole)
            qmb.setDefaultButton(ok)
            qmb.setEscapeButton(ok)
            qmb.exec_()
            if qmb.clickedButton() != emptyCommit:
                return

        initialText = self.state.getDraftCommitMessage()
        cd = CommitDialog(initialText, False, self)
        rc = cd.exec_()
        cd.deleteLater()
        if rc == QDialog.DialogCode.Accepted:
            porcelain.commit(self.repo, cd.getFullMessage())
            self.state.setDraftCommitMessage(None)  # Clear draft message
            self.quickRefresh()
        else:
            # Save draft message for next time
            self.state.setDraftCommitMessage(cd.getFullMessage())

    def amendFlow(self):
        initialText = porcelain.getHeadCommitMessage(self.repo)
        cd = CommitDialog(initialText, True, self)
        rc = cd.exec_()
        cd.deleteLater()
        if rc == QDialog.DialogCode.Accepted:
            porcelain.amend(self.repo, cd.getFullMessage())
            self.quickRefresh()

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
            if (message in meta.body.lower()) or (likelyHash and message in meta.hexsha):
                self.graphView.setCurrentIndex(modelIndex)
                return

        QMessageBox.information(self, "Find Commit", F"No more occurrences of “{message}”.")

    def findFlow(self):
        verbatimTerm, ok = textInputDialog(self, "Find Commit", "Search for partial commit hash or message:", self.previouslySearchedTerm)
        if not ok:
            return
        self.previouslySearchedTerm = verbatimTerm
        self._search(range(0, self.graphView.model().rowCount()))

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
            QMessageBox.warning(self, "Find in Patch", "Invalid search term.")
            return

        doc: QTextDocument = self.diffView.document()
        newCursor = doc.find(message, self.diffView.textCursor())
        if newCursor:
            self.diffView.setTextCursor(newCursor)
            return

        QMessageBox.information(self, "Find in Patch", F"No more occurrences of “{message}”.")

    def findInDiffFlow(self):
        verbatimTerm, ok = textInputDialog(self, "Find in Patch", "Search for text in current patch:", self.previouslySearchedTermInDiff)
        if not ok:
            return
        self.previouslySearchedTermInDiff = verbatimTerm
        self._searchDiff()

    def _findInDiffNextOrPrevious(self, findNext):
        if not sanitizeSearchTerm(self.previouslySearchedTermInDiff):
            QMessageBox.warning(self, "Find in Patch", "Please use “Find in Patch” to specify a search term before using “Find Next” or “Find Previous”.")
            return
        #if len(self.graphView.selectedIndexes()) == 0:
        #    QMessageBox.warning(self, "Find in Patch", "Please select a commit from whence to resume the search.")
        #    return
        self._searchInDiff(findNext)

    def findInDiffNext(self):
        self._findNextOrPrevious(True)

    def findInDiffPrevious(self):
        self._findNextOrPrevious(False)

    # -------------------------------------------------------------------------

    def quickRefresh(self):
        self.setUpdatesEnabled(False)

        with Benchmark("Load tainted commits only"):
            nRemovedRows, nAddedRows = self.state.loadTaintedCommitsOnly()

        with Benchmark("Refresh top of graphview"):
            self.graphView.refreshTop(nRemovedRows, nAddedRows, self.state.commitSequence)

        with Benchmark("Refresh refs by commit cache"):
            self.state.refreshRefsByCommitCache()

        self.setUpdatesEnabled(True)

        # force redraw visible portion of the graph view to reflect any changed tags/refs
        self.graphView.setDirtyRegion(QRegion(0, 0, self.graphView.width(), self.graphView.height()))

        if self.filesStack.currentIndex() == FILESSTACK_STAGE_CARD:
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
        if repo.head_is_detached:
            oid = porcelain.getHeadCommitOid(repo)
            inBrackets = F"detached HEAD @ {shortHash(oid)}"
        else:
            inBrackets = porcelain.getActiveBranchName(repo)
        self.window().setWindowTitle(F"{shortname} [{inBrackets}] — {settings.PROGRAM_NAME}")

    # -------------------------------------------------------------------------

    def selectRef(self, refName: str):
        oid = porcelain.getCommitOidFromReferenceName(self.repo, refName)
        self.graphView.selectCommit(oid)

    def selectTag(self, tagName: str):
        oid = porcelain.getCommitOidFromTagName(self.repo, tagName)
        self.graphView.selectCommit(oid)

    # -------------------------------------------------------------------------

    def openRescueFolder(self):
        trashPath = trash.getTrashPath(self.state.repo)
        if os.path.exists(trashPath):
            QDesktopServices.openUrl(QUrl(trashPath))
        else:
            QMessageBox.information(
                self,
                "Open Rescue Folder",
                "There’s no rescue folder for this repository. It might be that you’ve never "
                F"discarded a change using {settings.PROGRAM_NAME} yet."
            )
