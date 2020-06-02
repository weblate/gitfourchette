from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *
import git
import traceback
import os
from typing import List, Generator

import settings
import DiffActionSets
from util import fplural, compactRepoPath, showInFolder
import trash


class Entry:
    path: str
    label: str
    diff: git.Diff
    icon: str
    tooltip: str

    @classmethod
    def Tracked(cls, diff: git.Diff):
        entry = cls()
        entry.diff = diff
        entry.icon = diff.change_type
        # Prefer b_path; if it's a deletion, a_path may not be available
        entry.path = diff.b_path or diff.a_path
        entry.tooltip = str(diff)
        if settings.prefs.shortenDirectoryNames:
            entry.label = compactRepoPath(entry.path)
        else:
            entry.label = entry.path
        return entry

    @classmethod
    def Untracked(cls, path: str):
        entry = cls()
        entry.diff = None
        entry.path = path
        entry.icon = 'A'
        entry.tooltip = entry.path + '\n(untracked file)'
        if settings.prefs.shortenDirectoryNames:
            entry.label = compactRepoPath(entry.path)
        else:
            entry.label = entry.path
        return entry


class FileListView(QListView):
    nonEmptySelectionChanged: Signal = Signal()

    entries: List[Entry]
    diffActionSet: str

    def __init__(self, parent, diffActionSet=None):
        super().__init__(parent)
        self.entries = []
        self.repoWidget = parent
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        iconSize = self.fontMetrics().height()
        self.setIconSize(QSize(iconSize, iconSize))
        self.setEditTriggers(QAbstractItemView.NoEditTriggers) # prevent editing text after double-clicking
        self.diffActionSet = diffActionSet
        self.clear()

        self.setContextMenuPolicy(Qt.ActionsContextMenu)
        showInFolderAction = QAction("Open Containing Folder", self)
        showInFolderAction.triggered.connect(self.showInFolder)
        self.addAction(showInFolderAction)

    def showInFolder(self):
        for entry in self.selectedEntries():
            showInFolder(os.path.join(self.repo.working_tree_dir, entry.path))

    def clear(self):
        self.setModel(QStandardItemModel(self))  # do this instead of model.clear() to avoid triggering selectionChanged a million times
        self.entries.clear()

    def addEntry(self, entry):
        self.entries.append(entry)
        item = QStandardItem()
        item.setText(entry.label)
        item.setSizeHint(QSize(-1, self.fontMetrics().height()))  # Compact height
        item.setIcon(settings.statusIcons[entry.icon])
        if entry.tooltip:
            item.setToolTip(entry.tooltip)
        self.model().appendRow(item)

    def fillDiff(self, diffIndex: git.DiffIndex):
        for diff in diffIndex:
            self.addEntry(Entry.Tracked(diff))

    def fillUntracked(self, untracked: List[str]):
        for path in untracked:
            self.addEntry(Entry.Untracked(path))

    def selectFirstRow(self):
        if self.model().rowCount() == 0:
            self.repoWidget.diffView.clear()
            self.clearSelection()
        else:
            self.setCurrentIndex(self.model().index(0, 0))

    def selectionChanged(self, selected: QItemSelection, deselected: QItemSelection):
        super().selectionChanged(selected, deselected)

        indexes = list(selected.indexes())
        if len(indexes) == 0:
            return

        self.nonEmptySelectionChanged.emit()

        current = selected.indexes()[0]

        if not current.isValid():
            self.repoWidget.diffView.clear()
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()
        try:
            entry = self.entries[current.row()]
            if entry.diff is not None:
                self.repoWidget.diffView.setDiffContents(self.repo, entry.diff, self.diffActionSet)
            else:
                self.repoWidget.diffView.setUntrackedContents(self.repo, entry.path)
        except BaseException as ex:
            traceback.print_exc()
            self.repoWidget.diffView.setFailureContents(F"Error displaying diff: {repr(ex)}")
        QApplication.restoreOverrideCursor()

    def selectedEntries(self) -> Generator[Entry, None, None]:
        for si in self.selectedIndexes():
            yield self.entries[si.row()]

    @property
    def git(self):
        return self.repoWidget.state.repo.git

    @property
    def repo(self):
        return self.repoWidget.state.repo


class DirtyFileListView(FileListView):
    patchApplied: Signal = Signal()

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
        k = event.key()
        if k == Qt.Key_Return:
            self.stage()
        elif k == Qt.Key_Backspace or k == Qt.Key_Delete:
            self.discard()
        else:
            super().keyPressEvent(event)

    # Context menu action
    def stage(self):
        for entry in self.selectedEntries():
            self.git().add(entry.path)
        self.patchApplied.emit()

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
                trash.trashGitDiff(self.repo, entry.diff)
                self.git.restore(entry.path)  # self.diff.a_path)
            else:  # untracked file
                trash.trashUntracked(self.repo, entry.path)
                os.remove(os.path.join(self.repo.working_tree_dir, entry.path))
        self.patchApplied.emit()


class StagedFileListView(FileListView):
    patchApplied: Signal = Signal()

    def __init__(self, parent):
        super().__init__(parent, DiffActionSets.staged)
        self.setContextMenuPolicy(Qt.ActionsContextMenu)

        action = QAction("Unstage", self)
        action.triggered.connect(self.unstage)
        self.addAction(action)

    def keyPressEvent(self, event: QKeyEvent):
        k = event.key()
        if k == Qt.Key_Return or k == Qt.Key.Key_Backspace or k == Qt.Key.Key_Delete:
            self.unstage()
        else:
            super().keyPressEvent(event)

    def unstage(self):
        # everything that is staged is supposed to be a diff entry
        for entry in self.selectedEntries():
            assert entry.diff is not None
            self.git.restore(entry.diff.a_path, staged=True)
        self.patchApplied.emit()
