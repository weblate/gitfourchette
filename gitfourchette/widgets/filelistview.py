from allqt import *
from stagingstate import StagingState
from typing import Generator
from util import compactRepoPath, showInFolder, hasFlag, ActionDef, quickMenu, QSignalBlockerContext
import html
import pygit2
import os
import settings


class FileListView(QListView):
    nothingClicked = Signal()
    entryClicked = Signal(object, StagingState)

    entries: list[pygit2.Patch]
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

    def contextMenuEvent(self, event: QContextMenuEvent):
        if len(self.selectedIndexes()) == 0:
            return
        menu = quickMenu(self, self.createContextMenuActions())
        menu.exec_(event.globalPos())

    def createContextMenuActions(self):
        return [ActionDef("Open Containing &Folder", self.showInFolder)]

    def openFile(self):
        entries = list(self.selectedEntries())

        if len(entries) > 3 and QMessageBox.YesToAll != QMessageBox.question(
                self, "Open Many Files", F"Really open <b>{len(entries)}</b> files?",
                QMessageBox.YesToAll | QMessageBox.Cancel):
            return

        for entry in entries:
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.join(self.repo.workdir, entry.delta.new_file.path)))

    def showInFolder(self):
        entries = list(self.selectedEntries())

        if len(entries) > 3 and QMessageBox.YesToAll != QMessageBox.question(
                self, "Open Many Folders", F"Really open <b>{len(entries)}</b> folders?",
                QMessageBox.YesToAll | QMessageBox.Cancel):
            return

        for entry in self.selectedEntries():
            showInFolder(os.path.join(self.repo.workdir, entry.delta.new_file.path))

    def keyPressEvent(self, event: QKeyEvent):
        # The default keyPressEvent copies the displayed label of the selected items.
        # We want to copy the full path of the selected items instead.
        if event.matches(QKeySequence.Copy):
            self.copyPaths()
        else:
            super().keyPressEvent(event)

    def copyPaths(self):
        text = '\n'.join([entry.delta.new_file.path for entry in self.selectedEntries()])
        if text:
            QApplication.clipboard().setText(text)

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

    def addEntry(self, patch: pygit2.Patch):
        self.entries.append(patch)
        item = QStandardItem()

        delta: pygit2.DiffDelta = patch.delta
        path = patch.delta.new_file.path

        if settings.prefs.pathDisplayStyle == settings.PathDisplayStyle.ABBREVIATE_DIRECTORIES:
            label = compactRepoPath(path)
        elif settings.prefs.pathDisplayStyle == settings.PathDisplayStyle.SHOW_FILENAME_ONLY:
            label = path.rsplit('/', 1)[-1]
        else:
            label = path
        item.setText(label)

        item.setSizeHint(QSize(-1, self.fontMetrics().height()))  # Compact height

        if patch.delta.status == pygit2.GIT_DELTA_UNTRACKED:
            icon = settings.statusIcons.get('A', None)
        else:
            icon = settings.statusIcons.get(patch.delta.status_char(), None)
        if icon:
            item.setIcon(icon)

        tooltip = F"""
                        <b>from:</b> {html.escape(delta.old_file.path)} ({delta.old_file.mode:o})
                        <br><b>to:</b> {html.escape(delta.new_file.path)} ({delta.new_file.mode:o})
                        <br><b>operation:</b> {delta.status_char()}
                        <br><b>similarity:</b> {delta.similarity} (valid for R only)
                        """
        item.setToolTip(tooltip)

        self.model().appendRow(item)

    def addFileEntriesFromDiff(self, diff: pygit2.Diff):
        patch: pygit2.Patch
        for patch in diff:
            self.addEntry(patch)

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

    def selectedEntries(self) -> Generator[pygit2.Patch, None, None]:
        for si in self.selectedIndexes():
            yield self.entries[si.row()]

    @property
    def repo(self) -> pygit2.Repository:
        return self.repoWidget.state.repo

    def latestSelectedRow(self):
        try:
            return list(self.selectedIndexes())[-1].row()
        except IndexError:
            return None

