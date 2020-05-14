from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *
from RepoState import RepoState
from DiffView import DiffView
from TreeView import TreeView, UnstagedView, StagedView
from GraphView import GraphView
from RemoteProgress import RemoteProgress
from util import fplural
import traceback
import settings


class RepoWidget(QWidget):
    state: RepoState

    def __init__(self, parent):
        super().__init__(parent)

        self.state = None

        self.graphView = GraphView(self)
        self.filesStack = QStackedWidget()
        self.diffView = DiffView(self)
        self.changedFilesView = TreeView(self)
        self.dirtyView = UnstagedView(self)
        self.stageView = StagedView(self)

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
        commitButton = QPushButton("Commit")
        commitButton.clicked.connect(self.commitFlow)
        stageContainer.layout().addWidget(commitButton)
        stageSplitter = QSplitter(Qt.Vertical)
        stageSplitter.setHandleWidth(settings.splitterHandleWidth)
        stageSplitter.addWidget(dirtyContainer)
        stageSplitter.addWidget(stageContainer)

        self.filesStack.addWidget(self.changedFilesView)
        self.filesStack.addWidget(stageSplitter)
        self.filesStack.setCurrentIndex(0)

        bottomSplitter = QSplitter(Qt.Horizontal)
        bottomSplitter.setHandleWidth(settings.splitterHandleWidth)
        bottomSplitter.addWidget(self.filesStack)
        bottomSplitter.addWidget(self.diffView)
        bottomSplitter.setSizes([100, 300])

        mainSplitter = QSplitter(Qt.Vertical)
        mainSplitter.setHandleWidth(settings.splitterHandleWidth)
        mainSplitter.addWidget(self.graphView)
        mainSplitter.addWidget(bottomSplitter)
        mainSplitter.setSizes([100, 150])

        self.setLayout(QVBoxLayout())
        self.layout().addWidget(mainSplitter)

        mainSplitter.setObjectName("MainSplitter")
        bottomSplitter.setObjectName("BottomSplitter")
        stageSplitter.setObjectName("StageSplitter")
        self.splittersToSave = [mainSplitter, bottomSplitter, stageSplitter]
        for sts in self.splittersToSave:
            k = F"Splitters/{sts.objectName()}"
            if settings.appSettings.contains(k):
                sts.restoreState(settings.appSettings.value(k))

    def cleanup(self):
        self.state.repo.close()

    def saveSplitterStates(self):
        for sts in self.splittersToSave:
            settings.appSettings.setValue(F"Splitters/{sts.objectName()}", sts.saveState())

    def renameRepo(self):
        text, ok = QInputDialog().getText(
            self,
            "Rename repo", "Enter new nickname for repo:",
            QLineEdit.Normal,
            settings.getRepoNickname(self.state.dir)
        )
        if ok:
            settings.setRepoNickname(self.state.dir, text)

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

    def commitFlow(self):
        kDRAFT = "DraftMessage"
        dlg = QInputDialog(self)
        dlg.setInputMode(QInputDialog.TextInput)
        dlg.setWindowTitle("Commit")
        # absurdly-long label text because setMinimumWidth has no effect - we should probably make a custom dialog instead
        dlg.setLabelText("Enter commit message:                                                      ")
        dlg.setTextValue(self.state.settings.value(kDRAFT, ""))
        dlg.setOkButtonText("Commit")
        rc = dlg.exec_()
        message = dlg.textValue()
        if rc == QDialog.DialogCode.Accepted:
            self.state.settings.remove(kDRAFT)
            self.state.index.commit(message)
        else:
            self.state.settings.setValue(kDRAFT, message)
