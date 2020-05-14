from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *

import git
import settings
from util import fplural


class TreeViewEntry_Diff:
    def __init__(self, diff):
        self.diff = diff

    def clicked(self, rw):
        rw.diffView.setDiffContents(rw.state.repo, self.diff)

    def stage(self, rw):
        print(F"Staging: {self.diff.a_path}")
        # rw.state.index.add(self.diff.a_path) # <- also works at first... but might add too many things after repeated staging/unstaging??
        rw.state.repo.git.add(self.diff.a_path)

    def discard(self, rw):
        print(F"Discarding: {self.diff.a_path}")
        rw.state.repo.git.restore(self.diff.a_path)


class TreeViewEntry_Untracked:
    def __init__(self, path:str):
        self.path = path

    def clicked(self, rw):
        rw.diffView.setUntrackedContents(rw.state.repo, self.path)

    def stage(self, rw):
        rw.state.repo.git.add(self.path)

    def discard(self, rw):
        QMessageBox.warning(rw, "Discard not implemented", "Untracked: " + self.path)


class TreeView(QListView):
    entries = []

    def __init__(self, parent):
        super().__init__(parent)
        self.repoWidget = parent
        self.setModel(QStandardItemModel())
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setIconSize(QSize(16, 16))
        self.setEditTriggers(QAbstractItemView.NoEditTriggers) # prevent editing text after double-clicking

    def clear(self):
        #with self.uindo.unready():
        #self.model().clear()
        self.setModel(QStandardItemModel()) # do this instead of model.clear to avoid triggering selectionChanged a million times
        self.entries = []

    def fillDiff(self, diff: git.DiffIndex):
        model: QStandardItemModel = self.model()
        for f in diff:
            self.entries.append(TreeViewEntry_Diff(f))
            item = QStandardItem(f.a_path)
            item.setIcon(settings.statusIcons[f.change_type])
            model.appendRow(item)

    def fillUntracked(self, untracked_files):
        model: QStandardItemModel = self.model()
        for f in untracked_files:
            self.entries.append(TreeViewEntry_Untracked(f))
            item = QStandardItem(f + " (untracked)")
            item.setIcon(settings.statusIcons['A'])
            model.appendRow(item)

    def selectionChanged(self, selected: QItemSelection, deselected: QItemSelection):
        super().selectionChanged(selected, deselected)

        #if not self.repoWidget.isReady(): return

        indexes = list(selected.indexes())
        if len(indexes) == 0:
            return
        current = selected.indexes()[0]

        if not current.isValid():
            self.repoWidget.diffView.clear()
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()
        try:
            self.entries[current.row()].clicked(self.repoWidget)
        except BaseException as ex:
            import traceback
            traceback.print_exc()
            self.repoWidget.diffView.setFailureContents(F"Error displaying diff: {repr(ex)}")
        QApplication.restoreOverrideCursor()


class UnstagedView(TreeView):
    def __init__(self, parent):
        super().__init__(parent)
        self.setContextMenuPolicy(Qt.ActionsContextMenu)

        stageAction = QAction("Stage", self)
        stageAction.triggered.connect(self.stage)
        self.addAction(stageAction)

        discardAction = QAction("Discard changes", self)
        discardAction.triggered.connect(self.discard)
        self.addAction(discardAction)

    def stage(self):
        for si in self.selectedIndexes():
            self.entries[si.row()].stage(self.repoWidget)
        self.repoWidget.fillStageView()

    def discard(self):
        qmb = QMessageBox(
            QMessageBox.Question,
            "Discard changes",
            fplural(F"Really discard changes to # file^s?\nThis cannot be undone!", len(self.selectedIndexes())),
            QMessageBox.Yes | QMessageBox.Cancel)
        yes = qmb.button(QMessageBox.Yes)
        yes.setText("Discard changes")
        qmb.exec_()
        if qmb.clickedButton() != yes:
            return
        for si in self.selectedIndexes():
            self.entries[si.row()].discard(self.repoWidget)
        self.repoWidget.fillStageView()


class StagedView(TreeView):
    def __init__(self, parent):
        super().__init__(parent)
        self.setContextMenuPolicy(Qt.ActionsContextMenu)

        action = QAction("UnStage", self)
        action.triggered.connect(self.unstage)
        self.addAction(action)

    def unstage(self):
        # everything that is staged is supposed to be a diff entry
        git = self.repoWidget.state.repo.git
        for si in self.selectedIndexes():
            assert isinstance(self.entries[si.row()], TreeViewEntry_Diff)
            diff = self.entries[si.row()].diff
            print(F"UnStaging: {diff.a_path}")
            git.restore(diff.a_path, staged=True)
        self.repoWidget.fillStageView()
