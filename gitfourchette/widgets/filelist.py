from gitfourchette import settings
from gitfourchette.qt import *
from gitfourchette.stagingstate import StagingState
from gitfourchette.tempdir import getSessionTemporaryDirectory
from gitfourchette.util import (compactRepoPath, showInFolder, hasFlag, ActionDef, quickMenu, QSignalBlockerContext, shortHash, fplural as plur)
from pathlib import Path
from typing import Generator, Any
import bisect
import html
import os
import pygit2


# If SVG icons don't show up, you may need to install the 'qt6-svg' package.
STATUS_ICONS = {}
for status in "ACDMRTUX":
    STATUS_ICONS[status] = QIcon(F":/status_{status.lower()}.svg")


class FileListModel(QAbstractListModel):
    _diffs: list[pygit2.Diff]
    _diffStartRows: list[int]
    _fileRows: dict[str, int]
    _rows: int

    def __init__(self, parent):
        super().__init__(parent)
        self.clear()

    def clear(self):
        self._diffs = []
        self._diffStartRows = []
        self._fileRows = {}
        self._rows = 0
        self.modelReset.emit()

    def setDiffs(self, diffs: list[pygit2.Diff]):
        row = 0
        for diff in diffs:
            self._diffStartRows.append(row)
            self._diffs.append(diff)
            for patch in diff:
                self._fileRows[patch.delta.new_file.path] = row
                row += 1
        self._rows = row
        self.modelReset.emit()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return self._rows

    def getPatchAt(self, index: QModelIndex) -> pygit2.Patch:
        row = index.row()
        diffNo = bisect.bisect_right(self._diffStartRows, row) - 1
        fileNo = row - self._diffStartRows[diffNo]
        try:
            patch: pygit2.Patch = self._diffs[diffNo][fileNo]
            return patch
        except pygit2.GitError as e:
            print("GitError when attempting to get patch:", type(e).__name__, e)
            return None
        except OSError as e:
            # We might get here if the UI attempts to update itself while a long async
            # operation is ongoing. (e.g. a file is being recreated)
            print("UI attempting to update during async operation?", type(e).__name__, e)
            return None

    def getDeltaAt(self, index: QModelIndex) -> pygit2.DiffDelta:
        patch = self.getPatchAt(index)
        if patch:
            return patch.delta
        else:
            return None

    def data(self, index: QModelIndex, role: Qt.ItemDataRole = Qt.DisplayRole) -> Any:
        if role == Qt.UserRole:
            return self.getPatchAt(index)

        elif role == Qt.DisplayRole:
            delta = self.getDeltaAt(index)
            if not delta:
                return "<NO DELTA>"

            path: str = self.getDeltaAt(index).new_file.path
            if settings.prefs.pathDisplayStyle == settings.PathDisplayStyle.ABBREVIATE_DIRECTORIES:
                return compactRepoPath(path)
            elif settings.prefs.pathDisplayStyle == settings.PathDisplayStyle.SHOW_FILENAME_ONLY:
                return path.rsplit('/', 1)[-1]
            else:
                return path

        elif role == Qt.DecorationRole:
            delta = self.getDeltaAt(index)
            if not delta:
                return STATUS_ICONS.get('X', None)
            elif delta.status == pygit2.GIT_DELTA_UNTRACKED:
                return STATUS_ICONS.get('A', None)
            else:
                return STATUS_ICONS.get(delta.status_char(), None)

        elif role == Qt.ToolTipRole:
            delta = self.getDeltaAt(index)

            if not delta:
                return None

            if delta.status == pygit2.GIT_DELTA_UNTRACKED:
                return (
                    "<b>untracked file</b><br>" +
                    F"{html.escape(delta.new_file.path)} ({delta.new_file.mode:o})"
                )
            else:
                opSuffix = ""
                if delta.status == pygit2.GIT_DELTA_RENAMED:
                    opSuffix += F", {delta.similarity}% similarity"

                return (
                    F"<b>from:</b> {html.escape(delta.old_file.path)} ({delta.old_file.mode:o})"
                    F"<br><b>to:</b> {html.escape(delta.new_file.path)} ({delta.new_file.mode:o})"
                    F"<br><b>operation:</b> {delta.status_char()}{opSuffix}"
                )

        elif role == Qt.SizeHintRole:
            parentWidget: QWidget = self.parent()
            return QSize(-1, parentWidget.fontMetrics().height())

        return None

    def getRowForFile(self, path):
        return self._fileRows[path]


class FileList(QListView):
    nothingClicked = Signal()
    entryClicked = Signal(pygit2.Patch, StagingState)

    stagingState: StagingState

    def __init__(self, parent: QWidget, stagingState: StagingState):
        super().__init__(parent)
        self.setModel(FileListModel(self))
        self.stagingState = stagingState
        self.repoWidget = parent
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        iconSize = self.fontMetrics().height()
        self.setIconSize(QSize(iconSize, iconSize))
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)  # prevent editing text after double-clicking

    @property
    def flModel(self) -> FileListModel:
        return self.model()

    def setContents(self, diffs: list[pygit2.Diff]):
        self.flModel.setDiffs(diffs)

    def clear(self):
        self.flModel.clear()

    def contextMenuEvent(self, event: QContextMenuEvent):
        numIndexes = len(self.selectedIndexes())
        if numIndexes == 0:
            return
        menu = quickMenu(self, self.createContextMenuActions(numIndexes))
        menu.exec_(event.globalPos())

    def createContextMenuActions(self, count):
        return []

    def confirmSelectedEntries(self, text: str, threshold: int =3) -> list[pygit2.Patch]:
        entries = list(self.selectedEntries())

        if len(entries) <= threshold:
            return entries

        title = text.replace("#", "many").title()

        prompt = text.replace("#", F"<b>{len(entries)}</b>")
        prompt = F"Really {prompt}?"

        result = QMessageBox.question(self, title, prompt, QMessageBox.YesToAll | QMessageBox.Cancel)
        if result == QMessageBox.YesToAll:
            return entries
        else:
            return []

    def openFile(self):
        for entry in self.confirmSelectedEntries("open # files"):
            entryPath = os.path.join(self.repo.workdir, entry.delta.new_file.path)
            QDesktopServices.openUrl(QUrl.fromLocalFile(entryPath))

    def showInFolder(self):
        for entry in self.confirmSelectedEntries("open # folders"):
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

    def clearSelectionSilently(self):
        with QSignalBlockerContext(self):
            self.clearSelection()

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

        current: QModelIndex = selected.indexes()[0]
        if current.isValid():
            self.entryClicked.emit(current.data(Qt.UserRole), self.stagingState)
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
            self.scrollTo(self.indexAt(event.pos()))  # mousePressEvent won't scroll to the item on its own
        else:
            super().mouseMoveEvent(event)

    def selectedEntries(self) -> Generator[pygit2.Patch, None, None]:
        index: QModelIndex
        for index in self.selectedIndexes():
            patch: pygit2.Patch = index.data(Qt.UserRole)
            assert isinstance(patch, pygit2.Patch)
            yield patch

    @property
    def repo(self) -> pygit2.Repository:
        return self.repoWidget.state.repo

    def earliestSelectedRow(self):
        try:
            return list(self.selectedIndexes())[0].row()
        except IndexError:
            return -1

    def latestSelectedRow(self):
        try:
            return list(self.selectedIndexes())[-1].row()
        except IndexError:
            return -1

    def savePatchAs(self, saveInto=None):
        entries = list(self.selectedEntries())

        names = set()

        bigpatch = b""
        for diff in entries:
            if diff.delta.status == pygit2.GIT_DELTA_DELETED:
                diffFile = diff.delta.old_file
            else:
                diffFile = diff.delta.new_file
            if diff.data:
                bigpatch += diff.data
                names.add(Path(diffFile.path).stem)

        if not bigpatch:
            QApplication.beep()
            return

        name = ", ".join(sorted(names)) + ".patch"

        if saveInto:
            savePath = os.path.join(saveInto, name)
        else:
            savePath, _ = QFileDialog.getSaveFileName(self, "Save patch file", name)

        if not savePath:
            return

        with open(savePath, "wb") as f:
            f.write(bigpatch)

    def getFirstPath(self) -> str:
        model: FileListModel = self.model()
        index: QModelIndex = model.index(0)
        if index.isValid():
            return model.getPatchAt(index).delta.new_file.path
        else:
            return ""

    def selectFile(self, file: str):
        if not file:
            row = 0
        else:
            try:
                row = self.model().getRowForFile(file)
            except KeyError:
                return False

        self.selectRow(row)
        return True


class DirtyFiles(FileList):
    stageFiles = Signal(list)
    discardFiles = Signal(list)

    def __init__(self, parent):
        super().__init__(parent, StagingState.UNSTAGED)

        self.setSelectionMode(QAbstractItemView.ExtendedSelection)

    def createContextMenuActions(self, n):
        return [
            ActionDef(plur("&Stage #~File^s", n), self.stage, QStyle.SP_ArrowDown),
            ActionDef(plur("&Discard Changes", n), self.discard, QStyle.SP_TrashIcon),
            None,
            ActionDef(plur("&Open #~File^s in External Editor", n), self.openFile, icon=QStyle.SP_FileIcon),
            ActionDef("Save As Patch...", self.savePatchAs),
            None,
            ActionDef(plur("Open Containing Folder^s", n), self.showInFolder, icon=QStyle.SP_DirIcon),
            ActionDef(plur("&Copy Path^s", n), self.copyPaths),
        ]

    def keyPressEvent(self, event: QKeyEvent):
        k = event.key()
        if k in settings.KEYS_ACCEPT:
            self.stage()
        elif k in settings.KEYS_REJECT:
            self.discard()
        else:
            super().keyPressEvent(event)

    def stage(self):
        self.stageFiles.emit(list(self.selectedEntries()))

    def discard(self):
        self.discardFiles.emit(list(self.selectedEntries()))


class StagedFiles(FileList):
    unstageFiles: Signal = Signal(list)

    def __init__(self, parent):
        super().__init__(parent, StagingState.STAGED)

        self.setSelectionMode(QAbstractItemView.ExtendedSelection)

    def createContextMenuActions(self, n):
        return [
            ActionDef(plur("&Unstage #~File^s", n), self.unstage, QStyle.SP_ArrowUp),
            None,
            ActionDef(plur("&Open #~File^s in External Editor", n), self.openFile, QStyle.SP_FileIcon),
            ActionDef("Save As Patch...", self.savePatchAs),
            None,
            ActionDef(plur("Open Containing &Folder^s", n), self.showInFolder, QStyle.SP_DirIcon),
            ActionDef(plur("&Copy Path^s", n), self.copyPaths),
        ] + super().createContextMenuActions(n)

    def keyPressEvent(self, event: QKeyEvent):
        k = event.key()
        if k in settings.KEYS_ACCEPT + settings.KEYS_REJECT:
            self.unstage()
        else:
            super().keyPressEvent(event)

    def unstage(self):
        self.unstageFiles.emit(list(self.selectedEntries()))


class CommittedFiles(FileList):
    commitOid: pygit2.Oid | None

    def __init__(self, parent: QWidget):
        super().__init__(parent, StagingState.COMMITTED)
        self.commitOid = None

    def createContextMenuActions(self, n):
        return [
                ActionDef(plur("Open #~Revision^s in External Editor", n), self.openRevision, QStyle.SP_FileIcon),
                ActionDef(plur("Save Revision^s As...", n), self.saveRevisionAs, QStyle.SP_DialogSaveButton),
                ActionDef("Save As Patch...", self.savePatchAs),
                None,
                ActionDef(plur("Open Containing &Folder^s", n), self.showInFolder, QStyle.SP_DirIcon),
                ActionDef(plur("&Copy Path^s", n), self.copyPaths),
                ]

    def clear(self):
        super().clear()
        self.commitOid = None

    def setCommit(self, oid: pygit2.Oid):
        self.commitOid = oid

    def openRevision(self):
        for diff in self.confirmSelectedEntries("open # files"):
            diffFile: pygit2.DiffFile
            if diff.delta.status == pygit2.GIT_DELTA_DELETED:
                diffFile = diff.delta.old_file
            else:
                diffFile = diff.delta.new_file

            blob: pygit2.Blob = self.repo[diffFile.id].peel(pygit2.Blob)

            name, ext = os.path.splitext(os.path.basename(diffFile.path))
            name = F"{name}@{shortHash(self.commitOid)}{ext}"

            tempPath = os.path.join(getSessionTemporaryDirectory(), name)

            with open(tempPath, "wb") as f:
                f.write(blob.data)

            QDesktopServices.openUrl(QUrl.fromLocalFile(tempPath))

    def saveRevisionAs(self, saveInto=None):
        for diff in self.confirmSelectedEntries("save # files"):
            if diff.delta.status == pygit2.GIT_DELTA_DELETED:
                diffFile = diff.delta.old_file
            else:
                diffFile = diff.delta.new_file

            blob: pygit2.Blob = self.repo[diffFile.id].peel(pygit2.Blob)

            name, ext = os.path.splitext(os.path.basename(diffFile.path))
            name = F"{name}@{shortHash(self.commitOid)}{ext}"

            if saveInto:
                savePath = os.path.join(saveInto, name)
            else:
                savePath, _ = QFileDialog.getSaveFileName(self, "Save file revision", name)

            if not savePath:
                continue

            with open(savePath, "wb") as f:
                f.write(blob.data)

            os.chmod(savePath, diffFile.mode)
