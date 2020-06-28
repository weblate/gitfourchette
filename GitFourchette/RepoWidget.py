from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *
from RepoState import RepoState
from DiffView import DiffView
from FileListView import FileListView, DirtyFileListView, StagedFileListView
from GraphView import GraphView
from RemoteProgress import RemoteProgress
from util import fplural
from typing import List
import git
import traceback
import settings


PUSHINFO_FAILFLAGS = git.PushInfo.REJECTED | git.PushInfo.REMOTE_FAILURE | git.PushInfo.ERROR


class RepoWidget(QWidget):
    nameChange: Signal = Signal()

    state: RepoState

    def __init__(self, parent, sharedSplitterStates=None):
        super().__init__(parent)

        self.state = None

        self.graphView = GraphView(self)
        self.filesStack = QStackedWidget()
        self.diffView = DiffView(self)
        self.changedFilesView = FileListView(self)
        self.dirtyView = DirtyFileListView(self)
        self.stageView = StagedFileListView(self)

        self.stageView.nonEmptySelectionChanged.connect(lambda: self.dirtyView.clearSelection())
        self.dirtyView.nonEmptySelectionChanged.connect(lambda: self.stageView.clearSelection())

        # Refresh file list views after applying a patch...
        self.diffView.patchApplied.connect(self.fillStageView)  # ...from the diff view (partial line patch);
        self.stageView.patchApplied.connect(self.fillStageView)  # ...from the staged file view (unstage entire file);
        self.dirtyView.patchApplied.connect(self.fillStageView)  # ...and from the dirty file view (stage entire file).
        # Note that refreshing the file list views may, in turn, re-select a file from the appropriate file view,
        # which will trigger the diff view to be refreshed as well.

        self.splitterStates = sharedSplitterStates or {}

        self.dirtyLabel = QLabel("Dirty Files")
        self.stageLabel = QLabel("Files Staged For Commit")

        self.previouslySearchedTerm = None

        dirtyContainer = QWidget()
        dirtyContainer.setLayout(QVBoxLayout())
        dirtyContainer.layout().setContentsMargins(0,0,0,0)
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
        commitButton = QPushButton("Commit")
        commitButton.clicked.connect(self.commitFlow)
        commitButtonsContainer.layout().addWidget(commitButton)
        amendButton = QPushButton("Amend")
        amendButton.clicked.connect(self.amendFlow)
        commitButtonsContainer.layout().addWidget(amendButton)
        stageSplitter = QSplitter(Qt.Vertical)
        stageSplitter.setHandleWidth(settings.prefs.splitterHandleWidth)
        stageSplitter.addWidget(dirtyContainer)
        stageSplitter.addWidget(stageContainer)

        self.filesStack.addWidget(self.changedFilesView)
        self.filesStack.addWidget(stageSplitter)
        self.filesStack.setCurrentIndex(0)

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

        self.setLayout(QVBoxLayout())
        self.layout().setSpacing(0)
        self.layout().setMargin(0)
        self.layout().addWidget(mainSplitter)

        # object names are required for state saving to work
        mainSplitter.setObjectName("MainSplitter")
        bottomSplitter.setObjectName("BottomSplitter")
        stageSplitter.setObjectName("StageSplitter")
        self.splittersToSave = [mainSplitter, bottomSplitter, stageSplitter]
        # save splitter state in splitterMoved signal
        for splitter in self.splittersToSave:
            splitter.splitterMoved.connect(lambda pos, index, splitter=splitter: self.saveSplitterState(splitter))

        # remove frames for a cleaner look
        for w in self.graphView, self.diffView, self.dirtyView, self.stageView, self.changedFilesView:
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

    def cleanup(self):
        if self.state and self.state.repo:
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

    def fillStageView(self):
        """Fill Staged/Unstaged views with uncommitted changes"""

        self.dirtyView.clear()
        self.dirtyView.fillDiff(self.state.getDirtyChanges())
        self.dirtyView.fillUntracked(self.state.getUntrackedFiles())
        self.stageView.clear()
        self.stageView.fillDiff(self.state.getStagedChanges())  # R: prevent reversal

        nDirty = self.dirtyView.model().rowCount()
        nStaged = self.stageView.model().rowCount()
        self.dirtyLabel.setText(fplural(F"# dirty file^s:", nDirty))
        self.stageLabel.setText(fplural(F"# file^s staged for commit:", nStaged))

        self.filesStack.setCurrentIndex(1)

        # After patchApplied.emit has caused a refresh of the dirty/staged file views,
        # restore selected row in appropriate file list view so the user can keep hitting
        # enter (del) to stage (unstage) a series of files.
        self.dirtyView.restoreSelectedRowAfterClear()
        self.stageView.restoreSelectedRowAfterClear()

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
        pushInfos: List[git.PushInfo]

        try:
            pushInfos = remote.push(progress=progress)
        except BaseException as e:
            progress.close()
            traceback.print_exc()
            QMessageBox.critical(self, "Push",
                F"An exception was thrown while pushing.\n{e.__class__.__name__}: {e}.\nCheck stderr for details.")
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
            report = "Push successful!\n\n" + report
            QMessageBox.information(self, "Push successful", report)

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
        confirm, message = self._commitFlowDialog(
            self.state.settings.value(kDRAFT, ""), "Commit", "Enter commit message:", "Commit")
        if confirm:
            self.state.settings.remove(kDRAFT)
            #self.state.index.commit(message, amend=amend)
            self.state.repo.git.commit(m=message)
        else:
            self.state.settings.setValue(kDRAFT, message)

    def amendFlow(self):
        confirm, message = self._commitFlowDialog(
            self.state.repo.head.commit.message, "Amend", "Amend commit message:", "Amend")
        if confirm:
            self.state.repo.git.commit(m=message, amend=True)

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

        message = verbatimTerm.lower().strip()
        if not message:
            return

        self.previouslySearchedTerm = verbatimTerm

        likelyHash = False
        if len(message) <= 40:
            try:
                int(message, 16)
                likelyHash = True
            except ValueError:
                pass

        for i, meta in enumerate(self.state.order):
            if (message in meta.body.lower()) or (likelyHash and message in meta.hexsha):
                self.graphView.setCurrentIndex(self.graphView.model().index(1 + i, 0))
                return

        QApplication.beep()
