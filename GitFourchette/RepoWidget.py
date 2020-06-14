from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *
from RepoState import RepoState
from DiffView import DiffView
from FileListView import FileListView, DirtyFileListView, StagedFileListView
from GraphView import GraphView
from RemoteProgress import RemoteProgress
from util import fplural
import traceback
import settings


class RepoWidget(QWidget):
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

        self.diffView.patchApplied.connect(self.fillStageView)
        self.stageView.patchApplied.connect(self.fillStageView)
        self.dirtyView.patchApplied.connect(self.fillStageView)

        self.splitterStates = sharedSplitterStates or {}

        # windowVBox.setSpacing(0)
        # windowVBox.setContentsMargins(0, 0, 0, 0)

        self.dirtyLabel = QLabel("Dirty Files")
        self.stageLabel = QLabel("Files Staged For Commit")

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
        text, ok = QInputDialog().getText(
            self,
            "Rename repo", "Enter new nickname for repo:",
            QLineEdit.Normal,
            settings.history.getRepoNickname(self.state.dir)
        )
        if ok:
            settings.history.setRepoNickname(self.state.dir, text)

    def setNoCommitSelected(self):
        self.filesStack.setCurrentIndex(0)
        self.changedFilesView.clear()

    def fillStageView(self):
        """Fill Staged/Unstaged views with uncommitted changes"""

        self.dirtyView.clear()
        self.dirtyView.fillDiff(self.state.index.diff(None))
        self.dirtyView.fillUntracked(self.state.repo.untracked_files)
        self.stageView.clear()
        self.stageView.fillDiff(self.state.index.diff(self.state.repo.head.commit, R=True))  # R: prevent reversal

        nDirty = self.dirtyView.model().rowCount()
        nStaged = self.stageView.model().rowCount()
        self.dirtyLabel.setText(fplural(F"# dirty file^s:", nDirty))
        self.stageLabel.setText(fplural(F"# file^s staged for commit:", nStaged))

        self.filesStack.setCurrentIndex(1)

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
        try:
            remote.push(progress=progress)
        except BaseException as e:
            traceback.print_exc()
            QMessageBox.critical(self, "Error",
                F"An exception was thrown while pushing.\n{e.__class__.__name__}: {e}.\nCheck stderr for details.")

        progress.dlg.close()

    def _commitFlow(self, amend: bool):
        kDRAFT = "DraftMessage"
        dlg = QInputDialog(self)
        dlg.setInputMode(QInputDialog.TextInput)
        dlg.setWindowTitle("Amend" if amend else "Commit")
        # absurdly-long label text because setMinimumWidth has no effect - we should probably make a custom dialog instead
        dlg.setLabelText("Enter commit message:                                                      ")
        dlg.setTextValue(self.state.settings.value(kDRAFT, ""))
        dlg.setOkButtonText("Commit")
        rc = dlg.exec_()
        message = dlg.textValue()
        if rc == QDialog.DialogCode.Accepted:
            self.state.settings.remove(kDRAFT)
            #self.state.index.commit(message, amend=amend)
            self.state.repo.git.commit(m=message, amend=amend)
        else:
            self.state.settings.setValue(kDRAFT, message)

    def commitFlow(self):
        self._commitFlow(False)

    def amendFlow(self):
        self._commitFlow(True)
