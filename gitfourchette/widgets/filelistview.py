from allqt import *
from typing import Generator
from util import compactRepoPath, showInFolder, hasFlag
import git
import os
import settings


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

    entries: list[Entry]
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

    def fillUntracked(self, untracked: list[str]):
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

    def mouseMoveEvent(self, event: QMouseEvent):
        """
        By default, ExtendedSelection lets the user select multiple items by
        holding down LMB and dragging. This event handler enforces single-item
        selection unless the user holds down Shift or Ctrl.
        """
        isLMB = hasFlag(event.buttons(), Qt.LeftButton)
        isShift = hasFlag(event.modifiers(), Qt.ShiftModifier)
        isCtrl = hasFlag(event.modifiers(), Qt.ControlModifier)

        if isLMB and not isShift and not isCtrl:
            self.mousePressEvent(event)  # re-route event as if it were a click event
        else:
            super().mouseMoveEvent(event)

    def selectedEntries(self) -> Generator[Entry, None, None]:
        for si in self.selectedIndexes():
            yield self.entries[si.row()]

    @property
    def git(self):
        return self.repoWidget.state.repo.git

    @property
    def repo(self):
        return self.repoWidget.state.repo

