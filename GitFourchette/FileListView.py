from PySide6.QtCore import *
from PySide6.QtGui import *
from PySide6.QtWidgets import *
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
    nothingClicked = Signal()
    entryClicked = Signal(object, str)

    entries: List[Entry]
    diffActionSet: str
    selectedRowBeforeClear: int

    def __init__(self, parent, diffActionSet=None):
        super().__init__(parent)

        self.selectedRowBeforeClear = -1

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

    def _setBlankModel(self):
        if self.model():
            self.model().deleteLater()  # avoid memory leak
        # do this instead of model.clear() to avoid triggering selectionChanged a million times
        self.setModel(QStandardItemModel(self))

    def clear(self):
        # save selected index before clear so we can restore it after the widget is done being refreshed
        try:
            self.selectedRowBeforeClear = list(self.selectedIndexes())[-1].row()
        except IndexError:
            self.selectedRowBeforeClear = -1
        self._setBlankModel()
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
            self.nothingClicked.emit()
            self.clearSelection()
        else:
            self.setCurrentIndex(self.model().index(0, 0))

    def restoreSelectedRowAfterClear(self):
        rowCount = self.model().rowCount()
        if rowCount == 0 or self.selectedRowBeforeClear < 0:
            return

        if self.selectedRowBeforeClear >= rowCount:
            row = rowCount-1
        else:
            row = self.selectedRowBeforeClear

        self.setCurrentIndex(self.model().index(row, 0))

    def selectionChanged(self, selected: QItemSelection, deselected: QItemSelection):
        super().selectionChanged(selected, deselected)

        indexes = list(selected.indexes())
        if len(indexes) == 0:
            return

        self.nothingClicked.emit()

        current = selected.indexes()[0]
        if current.isValid():
            self.entryClicked.emit(self.entries[current.row()], self.diffActionSet)

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
        if k in settings.KEYS_ACCEPT:
            self.stage()
        elif k in settings.KEYS_REJECT:
            self.discard()
        else:
            super().keyPressEvent(event)

    # Context menu action
    def stage(self):
        for entry in self.selectedEntries():
            self.git.add(entry.path)
        self.patchApplied.emit()

    # Context menu action
    def discard(self):
        entries = list(self.selectedEntries())

        if len(entries) == 1:
            question = F"Really discard changes to {entries[0].path}?"
        else:
            question = F"Really discard changes to {len(entries)} files?"

        qmb = QMessageBox(
            QMessageBox.Question,
            "Discard changes",
            F"{question}\nThis cannot be undone!",
            QMessageBox.Yes | QMessageBox.Cancel,
            self)
        yes = qmb.button(QMessageBox.Yes)
        yes.setText("Discard changes")
        qmb.exec_()
        if qmb.clickedButton() != yes:
            return

        for entry in entries:
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
        if k in settings.KEYS_ACCEPT + settings.KEYS_REJECT:
            self.unstage()
        else:
            super().keyPressEvent(event)

    def unstage(self):
        # everything that is staged is supposed to be a diff entry
        for entry in self.selectedEntries():
            assert entry.diff is not None
            self.git.restore(entry.diff.a_path, staged=True)
        self.patchApplied.emit()
