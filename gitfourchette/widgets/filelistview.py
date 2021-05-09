from allqt import *
from filelistentry import FileListEntry
from stagingstate import StagingState
from typing import Generator
from util import compactRepoPath, showInFolder, hasFlag, QSignalBlockerContext
import git
import os
import settings


class FileListView(QListView):
    nothingClicked = Signal()
    entryClicked = Signal(object, StagingState)

    entries: list[FileListEntry]
    stagingState: StagingState

    def __init__(self, parent: QWidget, stagingState: StagingState):
        super().__init__(parent)

        self.stagingState = stagingState

        self.entries = []
        self.repoWidget = parent
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        iconSize = self.fontMetrics().height()
        self.setIconSize(QSize(iconSize, iconSize))
        self.setEditTriggers(QAbstractItemView.NoEditTriggers) # prevent editing text after double-clicking
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
        self._setBlankModel()
        self.entries.clear()

    def clearSelectionSilently(self):
        with QSignalBlockerContext(self):
            self.clearSelection()

    def addEntry(self, entry: FileListEntry):
        self.entries.append(entry)
        item = QStandardItem()
        if settings.prefs.pathDisplayStyle == settings.PathDisplayStyle.ABBREVIATE_DIRECTORIES:
            label = compactRepoPath(entry.path)
        elif settings.prefs.pathDisplayStyle == settings.PathDisplayStyle.SHOW_FILENAME_ONLY:
            label = entry.path.rsplit('/', 1)[-1]
        else:
            label = entry.path
        item.setText(label)
        item.setSizeHint(QSize(-1, self.fontMetrics().height()))  # Compact height
        item.setIcon(settings.statusIcons[entry.icon])
        if entry.tooltip:
            item.setToolTip(entry.tooltip)
        self.model().appendRow(item)

    def fillDiff(self, diffIndex: git.DiffIndex):
        for diff in diffIndex:
            self.addEntry(FileListEntry.Tracked(diff))

    def fillUntracked(self, untracked: list[str]):
        for path in untracked:
            self.addEntry(FileListEntry.Untracked(path))

    def selectRow(self, rowNumber=0):
        if self.model().rowCount() == 0:
            self.nothingClicked.emit()
            self.clearSelection()
        else:
            self.setCurrentIndex(self.model().index(rowNumber or 0, 0))

    def selectionChanged(self, selected: QItemSelection, deselected: QItemSelection):
        super().selectionChanged(selected, deselected)

        indexes = list(selected.indexes())
        if len(indexes) == 0:
            self.nothingClicked.emit()
            return

        current = selected.indexes()[0]
        if current.isValid():
            self.entryClicked.emit(self.entries[current.row()], self.stagingState)
        else:
            self.nothingClicked.emit()

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

    def selectedEntries(self) -> Generator[FileListEntry, None, None]:
        for si in self.selectedIndexes():
            yield self.entries[si.row()]

    # TODO: don't stage/unstage ourselves; expose stage/unstage events via signals
    @property
    def git(self):
        return self.repoWidget.state.repo.git

    @property
    def repo(self):
        return self.repoWidget.state.repo

    def latestSelectedRow(self):
        try:
            return list(self.selectedIndexes())[-1].row()
        except IndexError:
            return None

