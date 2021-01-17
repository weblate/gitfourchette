from PySide6.QtCore import *
from PySide6.QtGui import *
from PySide6.QtWidgets import *

import DiffActionSets
import DiffModel
from Benchmark import Benchmark
from RepoState import RepoState
from DiffView import DiffView
from FileListView import FileListView, DirtyFileListView, StagedFileListView
from GraphView import GraphView
from Sidebar import Sidebar
from RemoteProgress import RemoteProgress
from util import fplural, excMessageBox, excStrings
from typing import Callable
import git
import settings
import traceback
from Worker import Worker
from status import gstatus
from FileListView import Entry
from CommitDialog import CommitDialog


FILESSTACK_READONLY_CARD = 0
FILESSTACK_STAGE_CARD = 1

PUSHINFO_FAILFLAGS = git.PushInfo.REJECTED | git.PushInfo.REMOTE_FAILURE | git.PushInfo.ERROR


def sanitizeSearchTerm(x):
    if not x:
        return None
    return x.strip().lower()


def unimplementedDialog(featureName="UNIMPLEMENTED"):
    QMessageBox.warning(None, featureName, F"This feature isn't implemented yet\n({featureName})")


class RepoWidget(QWidget):
    nameChange: Signal = Signal()

    state: RepoState
    pathPending: str

    def __init__(self, parent, sharedSplitterStates=None):
        super().__init__(parent)

        # Thread pool for accessing the repo
        self.threadpool = QThreadPool(self)
        self.threadpool.setMaxThreadCount(1)

        self.state = None
        self.pathPending = None

        self.graphView = GraphView(self)
        self.filesStack = QStackedWidget()
        self.diffView = DiffView(self)
        self.changedFilesView = FileListView(self)
        self.dirtyView = DirtyFileListView(self)
        self.stageView = StagedFileListView(self)
        self.sidebar = Sidebar(self)

        self.stageView.nothingClicked.connect(self.dirtyView.clearSelection)
        self.dirtyView.nothingClicked.connect(self.stageView.clearSelection)

        # Refresh file list views after applying a patch...
        self.diffView.patchApplied.connect(self.fillStageViewAsync)  # ...from the diff view (partial line patch);
        self.stageView.patchApplied.connect(self.fillStageViewAsync)  # ...from the staged file view (unstage entire file);
        self.dirtyView.patchApplied.connect(self.fillStageViewAsync)  # ...and from the dirty file view (stage entire file).
        # Note that refreshing the file list views may, in turn, re-select a file from the appropriate file view,
        # which will trigger the diff view to be refreshed as well.

        for v in [self.dirtyView, self.stageView, self.changedFilesView]:
            v.nothingClicked.connect(self.diffView.clear)
            v.entryClicked.connect(self.loadDiffAsync)

        self.graphView.emptyClicked.connect(self.setNoCommitSelected)
        self.graphView.commitClicked.connect(self.loadCommitAsync)
        self.graphView.uncommittedChangesClicked.connect(self.fillStageViewAsync)

        self.sidebar.refClicked.connect(self.selectRef)
        self.sidebar.tagClicked.connect(self.selectTag)
        self.sidebar.checkOutBranch.connect(self.checkOutBranchAsync)
        self.sidebar.renameBranch.connect(self.renameBranchAsync)
        self.sidebar.mergeBranchIntoActive.connect(lambda name: unimplementedDialog("Merge Other Branch Into Active Branch"))
        self.sidebar.rebaseActiveOntoBranch.connect(lambda name: unimplementedDialog("Rebase Active Branch Into Other Branch"))
        self.sidebar.deleteBranch.connect(lambda name: unimplementedDialog("Delete Branch"))

        self.splitterStates = sharedSplitterStates or {}

        self.dirtyLabel = QLabel("Dirty Files")
        self.stageLabel = QLabel("Files Staged For Commit")

        self.previouslySearchedTerm = None

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

    @property
    def workingTreeDir(self):
        if self.state:
            return self.state.repo.working_tree_dir
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
            self.pathPending = str(self.state.repo.working_tree_dir)
            self.state.repo.close()
            self.state = None

    def renameRepo(self):
        qid = QInputDialog()
        text, ok = qid.getText(
            self,
            "Rename repo", "Enter new nickname for repo, or enter blank line to reset:",
            QLineEdit.Normal,
            settings.history.getRepoNickname(self.state.dir))
        if ok:
            settings.history.setRepoNickname(self.state.dir, text)
            self.nameChange.emit()

    def setNoCommitSelected(self):
        self.filesStack.setCurrentIndex(0)
        self.changedFilesView.clear()

    def _startAsyncWorker(
            self,
            priority: int,
            work: Callable[[], object],
            onComplete: Callable[[object], None],
            caption: str):
        """
        Starts a worker thread in the background, especially to perform
        long operations on the repository.

        Only one worker may be running at once; and only one worker may be
        queued at a time.

        :param priority: Integer value passed on to `QThreadPool.start()`.

        :param work: Function to run asynchronously. Returns an object.

        :param onComplete: Completion callback to run on the GUI thread when
        ``work`` is complete. Takes the object returned by ``work`` as its
        input parameter.

        :param caption: Shown in status.
        """

        # This callback gets executed when the worker's async function has completed successfully.
        def callback(o):
            # Clear status caption _before_ running onComplete,
            # because onComplete may start another worker that sets status.
            gstatus.clearIndeterminateProgressCaption()
            # Finally run completion
            if onComplete is not None:
                onComplete(o)

        def errorCallback(exc: BaseException):
            excMessageBox(exc, title=caption, message=F"Operation failed: {caption}")

        w = Worker(work)
        w.signals.result.connect(callback)
        w.signals.error.connect(errorCallback)
        gstatus.setIndeterminateProgressCaption(caption + "...")

        # Remove any pending worker from the queue.
        # TODO: we should prevent the currently-running worker's completion callback from running as well.
        self.threadpool.clear()

        # Queue our worker.
        self.threadpool.start(w, priority)

    def fillStageViewAsync(self):
        """Fill Staged/Unstaged views with uncommitted changes"""

        def work() -> tuple[git.DiffIndex, list[str], git.DiffIndex]:
            assert QThread.currentThread() is not QApplication.instance().thread()
            with self.state.mutexLocker():
                dirtyChanges = self.state.getDirtyChanges()
                untrackedFiles = self.state.getUntrackedFiles()
                stagedChanges = self.state.getStagedChanges()
            return dirtyChanges, untrackedFiles, stagedChanges

        def onComplete(result):
            assert QThread.currentThread() is QApplication.instance().thread()
            dirtyChanges, untrackedFiles, stagedChanges = result

            self.dirtyView.clear()
            self.dirtyView.fillDiff(dirtyChanges)
            self.dirtyView.fillUntracked(untrackedFiles)
            self.stageView.clear()
            self.stageView.fillDiff(stagedChanges)

            nDirty = self.dirtyView.model().rowCount()
            nStaged = self.stageView.model().rowCount()
            self.dirtyLabel.setText(fplural(F"# dirty file^s:", nDirty))
            self.stageLabel.setText(fplural(F"# file^s staged for commit:", nStaged))

            self.filesStack.setCurrentIndex(FILESSTACK_STAGE_CARD)

            # After patchApplied.emit has caused a refresh of the dirty/staged file views,
            # restore selected row in appropriate file list view so the user can keep hitting
            # enter (del) to stage (unstage) a series of files.
            self.dirtyView.restoreSelectedRowAfterClear()
            self.stageView.restoreSelectedRowAfterClear()

            # If no file is selected in either FileListView, clear the diffView of any residual diff.
            if 0 == (len(self.dirtyView.selectedIndexes()) + len(self.stageView.selectedIndexes())):
                self.diffView.clear()

        self._startAsyncWorker(1000, work, onComplete, "Refreshing index")

    def loadCommitAsync(self, hexsha: str):
        """Load commit details into Changed Files view"""

        def work() -> list[git.DiffIndex]:
            assert QThread.currentThread() is not QApplication.instance().thread()
            with self.state.mutexLocker():
                commit = self.state.repo.commit(hexsha)
                return [p.diff(commit) for p in commit.parents]

        def onComplete(parentDiffs):
            assert QThread.currentThread() is QApplication.instance().thread()
            self.changedFilesView.clear()
            for d in parentDiffs:
                self.changedFilesView.fillDiff(d)
            self.changedFilesView.selectFirstRow()
            self.filesStack.setCurrentIndex(0)

        self._startAsyncWorker(1000, work, onComplete, F"Loading commit “{hexsha[:settings.prefs.shortHashChars]}”")

    def loadDiffAsync(self, entry, diffActionSet):
        """Load a file diff into the Diff View"""

        repo = self.state.repo

        def work():
            assert QThread.currentThread() is not QApplication.instance().thread()
            with self.state.mutexLocker():
                try:
                    if entry.diff is not None:
                        allowRawFileAccess = diffActionSet in DiffActionSets.allowRawFileAccess
                        dm = DiffModel.fromGitDiff(repo, entry.diff, allowRawFileAccess)
                    else:
                        dm = DiffModel.fromUntrackedFile(repo, entry.path)
                except BaseException as exc:
                    summary, details = excStrings(exc)
                    dm = DiffModel.fromFailureMessage(summary, details)
                dm.document.moveToThread(QApplication.instance().thread())
                return dm

        def onComplete(dm):
            assert QThread.currentThread() is QApplication.instance().thread()
            self.diffView.replaceDocument(repo, entry.diff, diffActionSet, dm)

        self._startAsyncWorker(0, work, onComplete, F"Loading diff “{entry.path}”")

    def checkOutBranchAsync(self, newBranch: str):
        repo = self.state.repo

        def work():
            with self.state.mutexLocker():
                repo.git.checkout(newBranch)

        def onComplete(_):
            self.quickRefresh()
            self.sidebar.fill(repo)

        self._startAsyncWorker(2000, work, onComplete, F"Checking out branch “{newBranch}”")

    def renameBranchAsync(self, oldName:str, newName:str):
        repo = self.state.repo

        def work():
            with self.state.mutexLocker():
                # TODO: if the branch tracks an upstream branch, issue a warning that it won't be renamed on the server
                repo.git.branch(oldName, newName, m=True)

        def onComplete(_):
            self.quickRefresh()
            self.sidebar.fill(repo)

        self._startAsyncWorker(2000, work, onComplete, F"Renaming branch “{oldName}” to “{newName}”")

    # -------------------------------------------------------------------------
    # Push

    def push(self):
        repo = self.state.repo
        branch = repo.active_branch
        tracking = repo.active_branch.tracking_branch()
        remote = repo.remote(tracking.remote_name)
        urls = list(remote.urls)

        qmb = QMessageBox(self)
        qmb.setWindowTitle("Push")
        qmb.setIcon(QMessageBox.Question)
        qmb.setText(F"""Confirm Push?
To remote: "{remote.name}" at {'; '.join(urls)}
Branch: "{branch.name}" tracking "{tracking.name}" """)
        qmb.addButton("Push", QMessageBox.AcceptRole)
        qmb.addButton("Cancel", QMessageBox.RejectRole)
        if qmb.exec_() != QMessageBox.AcceptRole:
            return

        progress = RemoteProgress(self, "Push in progress")
        pushInfos: list[git.PushInfo]

        try:
            pushInfos = remote.push(progress=progress)
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

    def _commitFlowDialog(self, initialText, title, prompt, buttonCaption) -> (bool, str):
        while True:
            dlg = QInputDialog(self)
            dlg.setInputMode(QInputDialog.TextInput)
            dlg.setWindowTitle(title)
            # absurdly-long label text because setMinimumWidth has no effect - we should probably make a custom dialog instead
            dlg.setLabelText(prompt + (" "*50))
            dlg.setTextValue(initialText)
            dlg.setOkButtonText(buttonCaption)

            rc = dlg.exec_()
            accepted = rc == QDialog.DialogCode.Accepted

            message = dlg.textValue()
            dlg.deleteLater()  # avoid leaking dialog (can't use WA_DeleteOnClose because we needed to retrieve the message)

            if rc == QDialog.DialogCode.Accepted and not message.strip():
                rc2 = QMessageBox.warning(
                    self, title + " failed", "The commit message cannot be empty.",
                    QMessageBox.Retry | QMessageBox.Cancel, QMessageBox.Retry)
                if rc2 == QMessageBox.Retry:
                    continue
                else:
                    accepted = False

            return accepted, message

    def commitFlow(self):
        if 0 == len(self.state.getStagedChanges()):
            QMessageBox.warning(self, "Commit", "No changes staged for commit.")
            return

        kDRAFT = "DraftMessage"
        initialText = self.state.settings.value(kDRAFT, "")
        cd = CommitDialog(initialText, False, self)
        rc = cd.exec_()
        cd.deleteLater()
        if rc == QDialog.DialogCode.Accepted:
            self.state.settings.remove(kDRAFT)
            self.state.repo.git.commit(message=cd.getFullMessage())
            self.quickRefresh()
        else:
            self.state.settings.setValue(kDRAFT, cd.getFullMessage())

    def amendFlow(self):
        initialText = self.state.repo.head.commit.message
        cd = CommitDialog(initialText, True, self)
        rc = cd.exec_()
        cd.deleteLater()
        if rc == QDialog.DialogCode.Accepted:
            self.state.repo.git.commit(message=cd.getFullMessage(), amend=True)
            self.quickRefresh()

    # -------------------------------------------------------------------------
    # Find, find next

    def _search(self, searchRange):
        message = self.previouslySearchedTerm
        message = sanitizeSearchTerm(message)
        if not message:
            QMessageBox.warning(self, "Find", "Invalid search term.")
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

        QMessageBox.information(self, "Find", F"No more occurrences of “{message}”.")

    def findFlow(self):
        dlg = QInputDialog(self)
        dlg.setInputMode(QInputDialog.TextInput)
        dlg.setWindowTitle("Find Commit")
        dlg.setLabelText("Search for partial commit hash or message:")
        if self.previouslySearchedTerm:
            dlg.setTextValue(self.previouslySearchedTerm)
        dlg.setOkButtonText("Find")
        rc = dlg.exec_()
        verbatimTerm: str = dlg.textValue()
        dlg.deleteLater()  # avoid leaking dialog (can't use WA_DeleteOnClose because we needed to retrieve the message)
        if rc != QDialog.DialogCode.Accepted:
            return
        self.previouslySearchedTerm = verbatimTerm
        self._search(range(0, self.graphView.model().rowCount()))

    def _findNextOrPrevious(self, findNext):
        if not sanitizeSearchTerm(self.previouslySearchedTerm):
            QMessageBox.warning(self, "Find", "Please use “Find” to specify a search term before using “Find Next” or “Find Previous”.")
            return
        if len(self.graphView.selectedIndexes()) == 0:
            QMessageBox.warning(self, "Find", "Please select a commit from whence to resume the search.")
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

    def quickRefresh(self):
        frontTrim, frontNewMetas = self.state.loadTaintedCommitsOnly()
        if not frontNewMetas:
            assert frontTrim == 0
        else:
            self.graphView.patchFill(frontTrim, frontNewMetas)

        self.state.refreshRefsByCommitCache()

        # force redraw visible portion of the graph view to reflect any changed tags/refs
        self.graphView.setDirtyRegion(QRegion(0, 0, self.graphView.width(), self.graphView.height()))

        if self.filesStack.currentIndex() == FILESSTACK_STAGE_CARD:
            self.fillStageViewAsync()
        gstatus.clearProgress()

    # -------------------------------------------------------------------------

    def selectCommit(self, commitHash: str):
        model = self.graphView.model()
        for i in range(model.rowCount()):
            modelIndex = model.index(i, 0)
            meta = model.data(modelIndex)
            if meta is None:
                continue
            if commitHash == meta.hexsha:
                self.graphView.setCurrentIndex(modelIndex)
                return
        QApplication.beep()

    def selectRef(self, refName: str):
        repo = self.state.repo
        ref: git.Reference = next(filter(lambda ref: ref.name == refName, repo.refs))
        self.selectCommit(ref.commit.hexsha)

    def selectTag(self, tagName: str):
        repo = self.state.repo
        tag: git.Tag = next(filter(lambda tag: tag.name == tagName, repo.tags))
        self.selectCommit(tag.commit.hexsha)

