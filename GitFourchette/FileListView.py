from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *
import git
import traceback
from typing import List, Generator

import settings
import DiffActionSets
from util import fplural


class Entry:
    path: str
    diff: git.Diff
    icon: str

    @classmethod
    def Tracked(cls, diff: git.Diff):
        entry = cls()
        entry.diff = diff
        entry.path = diff.a_path
        entry.icon = diff.change_type
        return entry

    @classmethod
    def Untracked(cls, path: str):
        entry = cls()
        entry.diff = None
        entry.path = path
        entry.icon = 'A'
        return entry


class FileListView(QListView):
    entries: List[Entry]
    diffActionSet: str

    def __init__(self, parent, diffActionSet=None):
        super().__init__(parent)
        self.entries = []
        self.repoWidget = parent
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setIconSize(QSize(16, 16))
        self.setEditTriggers(QAbstractItemView.NoEditTriggers) # prevent editing text after double-clicking
        self.diffActionSet = diffActionSet
        self.clear()

    def clear(self):
        self.setModel(QStandardItemModel(self))  # do this instead of model.clear() to avoid triggering selectionChanged a million times
        self.entries.clear()

    def addEntry(self, entry):
        self.entries.append(entry)
        item = QStandardItem()
        item.setText(entry.path)
        item.setIcon(settings.statusIcons[entry.icon])
        self.model().appendRow(item)

    def fillDiff(self, diffIndex: git.DiffIndex):
        for diff in diffIndex:
            self.addEntry(self.Entry.Tracked(diff))

    def fillUntracked(self, untracked: List[str]):
        for path in untracked:
            self.addEntry(self.Entry.Untracked(path))

    def selectionChanged(self, selected: QItemSelection, deselected: QItemSelection):
        super().selectionChanged(selected, deselected)

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
            entry = self.entries[current.row()]
            if entry.diff is not None:
                self.repoWidget.diffView.setDiffContents(self.repoWidget.state.repo, entry.diff, self.diffActionSet)
            else:
                self.repoWidget.diffView.setUntrackedContents(self.repoWidget.state.repo, entry.path)
        except BaseException as ex:
            traceback.print_exc()
            self.repoWidget.diffView.setFailureContents(F"Error displaying diff: {repr(ex)}")
        QApplication.restoreOverrideCursor()

    def selectedEntries(self) -> Generator[Entry, None, None]:
        for si in self.selectedIndexes():
            yield self.entries[si.row()]

    def git(self):
        return self.repoWidget.state.repo.git


class DirtyFileListView(FileListView):
    def __init__(self, parent):
        super().__init__(parent, DiffActionSets.unstaged)
        self.setContextMenuPolicy(Qt.ActionsContextMenu)

        stageAction = QAction("Stage", self)
        stageAction.triggered.connect(self.stage)
        self.addAction(stageAction)

        discardAction = QAction("Discard changes", self)
        discardAction.triggered.connect(self.discard)
        self.addAction(discardAction)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Return:
            self.stage()
        else:
            super().keyPressEvent(event)

    # Context menu action
    def stage(self):
        for entry in self.selectedEntries():
            self.git().add(entry.path)
        self.repoWidget.fillStageView()

    # Context menu action
    def discard(self):
        qmb = QMessageBox(
            QMessageBox.Question,
            "Discard changes",
            fplural(F"Really discard changes to # file^s?\nThis cannot be undone!", len(self.selectedIndexes())),
            QMessageBox.Yes | QMessageBox.Cancel,
            self)
        yes = qmb.button(QMessageBox.Yes)
        yes.setText("Discard changes")
        qmb.exec_()
        if qmb.clickedButton() != yes:
            return

        for entry in self.selectedEntries():
            if entry.diff is not None:  # tracked file
                self.git().restore(entry.path)  # self.diff.a_path)
            else:  # untracked file
                QMessageBox.warning(self, "Discard", "Discard not implemented for untracked files: " + entry.path)
        self.repoWidget.fillStageView()


class StagedFileListView(FileListView):
    def __init__(self, parent):
        super().__init__(parent, DiffActionSets.staged)
        self.setContextMenuPolicy(Qt.ActionsContextMenu)

        action = QAction("Unstage", self)
        action.triggered.connect(self.unstage)
        self.addAction(action)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Return:
            self.unstage()
        else:
            super().keyPressEvent(event)

    def unstage(self):
        # everything that is staged is supposed to be a diff entry
        for entry in self.selectedEntries():
            assert entry.diff is not None
            self.git().restore(entry.diff.a_path, staged=True)
        self.repoWidget.fillStageView()
