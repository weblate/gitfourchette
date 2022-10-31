from dataclasses import dataclass
from gitfourchette import log
from gitfourchette import settings
from gitfourchette.qt import *
from gitfourchette.stagingstate import StagingState
from gitfourchette.tempdir import getSessionTemporaryDirectory
from gitfourchette.util import (abbreviatePath, showInFolder, hasFlag, ActionDef, quickMenu, QSignalBlockerContext, shortHash, PersistentFileDialog)
from pathlib import Path
from typing import Generator, Any
import errno
import html
import os
import pygit2


# If SVG icons don't show up, you may need to install the 'qt6-svg' package.
STATUS_ICONS = {}
for status in "ACDMRTUX":
    STATUS_ICONS[status] = QIcon(F"assets:status_{status.lower()}.svg")

FALLBACK_STATUS_ICON = QIcon("assets:status_fallback.svg")


class FileListModel(QAbstractListModel):
    @dataclass
    class Entry:
        delta: pygit2.DiffDelta
        diff: pygit2.Diff
        patchNo: int

    entries: list[Entry]
    fileRows: dict[str, int]

    def __init__(self, parent):
        super().__init__(parent)
        self.clear()

    def clear(self):
        self.entries = []
        self.fileRows = {}
        self.modelReset.emit()

    def setDiffs(self, diffs: list[pygit2.Diff]):
        for diff in diffs:
            for patchNo, delta in enumerate(diff.deltas):
                # In merge commits, the same file may appear in several diffs
                if delta.new_file.path in self.fileRows:
                    continue
                self.fileRows[delta.new_file.path] = len(self.entries)
                self.entries.append(FileListModel.Entry(delta, diff, patchNo))

        self.modelReset.emit()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self.entries)

    def getPatchAt(self, index: QModelIndex) -> pygit2.Patch:
        row = index.row()
        entry = self.entries[row]
        try:
            patch: pygit2.Patch = entry.diff[entry.patchNo]
            return patch
        except pygit2.GitError as e:
            log.warning("FileList", "GitError when attempting to get patch:", type(e).__name__, e)
            return None
        except OSError as e:
            # We might get here if the UI attempts to update itself while a long async
            # operation is ongoing. (e.g. a file is being recreated)
            log.warning("FileList", "UI attempting to update during async operation?", type(e).__name__, e)
            return None

    def getDeltaAt(self, index: QModelIndex) -> pygit2.DiffDelta:
        return self.entries[index.row()].delta

    def data(self, index: QModelIndex, role: Qt.ItemDataRole = Qt.ItemDataRole.DisplayRole) -> Any:
        if role == Qt.ItemDataRole.UserRole:
            return self.getPatchAt(index)

        elif role == Qt.ItemDataRole.DisplayRole:
            delta = self.getDeltaAt(index)
            if not delta:
                return "<NO DELTA>"

            path: str = self.getDeltaAt(index).new_file.path
            return abbreviatePath(path, settings.prefs.pathDisplayStyle)

        elif role == Qt.ItemDataRole.DecorationRole:
            delta = self.getDeltaAt(index)
            if not delta:
                return FALLBACK_STATUS_ICON
            elif delta.status == pygit2.GIT_DELTA_UNTRACKED:
                return STATUS_ICONS.get('A', FALLBACK_STATUS_ICON)
            else:
                return STATUS_ICONS.get(delta.status_char(), FALLBACK_STATUS_ICON)

        elif role == Qt.ItemDataRole.ToolTipRole:
            delta = self.getDeltaAt(index)

            if not delta:
                return None

            if delta.status == pygit2.GIT_DELTA_UNTRACKED:
                return (
                    "<b>" + self.tr("untracked file") + "</b><br>" +
                    F"{html.escape(delta.new_file.path)} ({delta.new_file.mode:o})"
                )
            else:
                fromText = self.tr("from:")
                toText = self.tr("to:")
                opText = self.tr("operation:")

                operationCaptions = {
                    "A": self.tr("(added)"),
                    "C": self.tr("(copied)"),
                    "D": self.tr("(deleted)"),
                    "M": self.tr("(modified)"),
                    "R": self.tr("(renamed, {0}% similarity)"),
                    "T": self.tr("(file type changed)"),
                    "U": self.tr("(updated but unmerged)"),
                }

                try:
                    opCap = operationCaptions[delta.status_char()]
                    if delta.status == pygit2.GIT_DELTA_RENAMED:
                        opCap = opCap.format(delta.similarity)

                except KeyError:
                    opCap = ''

                return (
                    F"<b>{fromText} </b> {html.escape(delta.old_file.path)} ({delta.old_file.mode:o})"
                    F"<br><b>{toText} </b> {html.escape(delta.new_file.path)} ({delta.new_file.mode:o})"
                    F"<br><b>{opText} </b> {delta.status_char()} {opCap}"
                )

        elif role == Qt.ItemDataRole.SizeHintRole:
            parentWidget: QWidget = self.parent()
            return QSize(-1, parentWidget.fontMetrics().height())

        return None

    def getRowForFile(self, path):
        return self.fileRows[path]


class FileList(QListView):
    nothingClicked = Signal()
    entryClicked = Signal(pygit2.Patch, StagingState)

    stagingState: StagingState

    def __init__(self, parent: QWidget, stagingState: StagingState):
        super().__init__(parent)
        self.setModel(FileListModel(self))
        self.stagingState = stagingState
        self.repoWidget = parent
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        iconSize = self.fontMetrics().height()
        self.setIconSize(QSize(iconSize, iconSize))
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)  # prevent editing text after double-clicking

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
        menu.setObjectName("FileListContextMenu")
        menu.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        menu.exec_(event.globalPos())

    def createContextMenuActions(self, count):
        return []

    def confirmSelectedEntries(self, prompt: str, threshold: int = 3) -> list[pygit2.Patch]:
        entries = list(self.selectedEntries())

        if len(entries) <= threshold:
            return entries

        numFiles = len(entries)
        title = self.tr("{0} files selected").format(numFiles) # with %n, self.tr doesn't work here for some reason...

        result = QMessageBox.question(self, title, prompt.format(numFiles), QMessageBox.StandardButton.YesToAll | QMessageBox.StandardButton.Cancel)
        if result == QMessageBox.StandardButton.YesToAll:
            return entries
        else:
            return []

    def openFile(self):
        for entry in self.confirmSelectedEntries(self.tr("Really open {0} files in external editor?")):
            entryPath = os.path.join(self.repo.workdir, entry.delta.new_file.path)
            QDesktopServices.openUrl(QUrl.fromLocalFile(entryPath))

    def showInFolder(self):
        for entry in self.confirmSelectedEntries(self.tr("Really open {0} folders?")):
            showInFolder(os.path.join(self.repo.workdir, entry.delta.new_file.path))

    def keyPressEvent(self, event: QKeyEvent):
        # The default keyPressEvent copies the displayed label of the selected items.
        # We want to copy the full path of the selected items instead.
        if event.matches(QKeySequence.StandardKey.Copy):
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
            self.entryClicked.emit(current.data(Qt.ItemDataRole.UserRole), self.stagingState)
        else:
            self.nothingClicked.emit()

    def mouseMoveEvent(self, event: QMouseEvent):
        """
        By default, ExtendedSelection lets the user select multiple items by
        holding down LMB and dragging. This event handler enforces single-item
        selection unless the user holds down Shift or Ctrl.
        """
        isLMB = hasFlag(event.buttons(), Qt.MouseButton.LeftButton)
        isShift = hasFlag(event.modifiers(), Qt.KeyboardModifier.ShiftModifier)
        isCtrl = hasFlag(event.modifiers(), Qt.KeyboardModifier.ControlModifier)

        if isLMB and not isShift and not isCtrl:
            self.mousePressEvent(event)  # re-route event as if it were a click event
            self.scrollTo(self.indexAt(event.pos()))  # mousePressEvent won't scroll to the item on its own
        else:
            super().mouseMoveEvent(event)

    def selectedEntries(self) -> Generator[pygit2.Patch, None, None]:
        index: QModelIndex
        for index in self.selectedIndexes():
            patch: pygit2.Patch = index.data(Qt.ItemDataRole.UserRole)
            if not patch:
                raise ValueError(self.tr("This file appears to have changed since we last read it. Try refreshing the window."))
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
            savePath, _ = PersistentFileDialog.getSaveFileName(self, self.tr("Save patch file"), name)

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

    def openRevisionPriorToChange(self):
        for diff in self.confirmSelectedEntries(self.tr("Really open {0} files in external editor?")):
            diffFile: pygit2.DiffFile = diff.delta.old_file

            blob: pygit2.Blob = self.repo[diffFile.id].peel(pygit2.Blob)

            name, ext = os.path.splitext(os.path.basename(diffFile.path))
            name = F"{name}[lastcommit]{ext}"

            tempPath = os.path.join(getSessionTemporaryDirectory(), name)

            with open(tempPath, "wb") as f:
                f.write(blob.data)

            QDesktopServices.openUrl(QUrl.fromLocalFile(tempPath))


class DirtyFiles(FileList):
    stageFiles = Signal(list)
    discardFiles = Signal(list)

    def __init__(self, parent):
        super().__init__(parent, StagingState.UNSTAGED)

        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

    def createContextMenuActions(self, n):
        return [
            ActionDef(self.tr("&Stage %n File(s)", "", n), self.stage, QStyle.StandardPixmap.SP_ArrowDown),
            ActionDef(self.tr("&Discard Changes", "", n), self.discard, QStyle.StandardPixmap.SP_TrashIcon),
            None,
            ActionDef(self.tr("&Open %n File(s) in External Editor", "", n), self.openFile, icon=QStyle.StandardPixmap.SP_FileIcon),
            ActionDef(self.tr("Export As Patch..."), self.savePatchAs),
            None,
            ActionDef(self.tr("Open Containing Folder(s)", "", n), self.showInFolder, icon=QStyle.StandardPixmap.SP_DirIcon),
            ActionDef(self.tr("&Copy Path(s)", "", n), self.copyPaths),
            None,
            ActionDef(self.tr("Open Unmodified &Revision(s) in External Editor", "", n), self.openRevisionPriorToChange),
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

        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

    def createContextMenuActions(self, n):
        return [
            ActionDef(self.tr("&Unstage %n File(s)", "", n), self.unstage, QStyle.StandardPixmap.SP_ArrowUp),
            None,
            ActionDef(self.tr("&Open %n File(s) in External Editor", "", n), self.openFile, QStyle.StandardPixmap.SP_FileIcon),
            ActionDef(self.tr("Export As Patch..."), self.savePatchAs),
            None,
            ActionDef(self.tr("Open Containing &Folder(s)", "", n), self.showInFolder, QStyle.StandardPixmap.SP_DirIcon),
            ActionDef(self.tr("&Copy Path(s)", "", n), self.copyPaths),
            None,
            ActionDef(self.tr("Open Unmodified &Revision(s) in External Editor", "", n), self.openRevisionPriorToChange),
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
                ActionDef(self.tr("&Open Revision(s)...", "", n), icon=QStyle.StandardPixmap.SP_FileIcon, submenu=
                [
                    ActionDef(self.tr("&At Commit"), self.openNewRevision),
                    ActionDef(self.tr("&Before Commit"), self.openOldRevision),
                    None,
                    ActionDef(self.tr("&Current (working directory)"), self.openHeadRevision),
                ]),
                ActionDef(self.tr("&Save Revision(s)...", "", n), icon=QStyle.StandardPixmap.SP_DialogSaveButton, submenu=
                [
                    ActionDef(self.tr("&At Commit"), self.saveNewRevision),
                    ActionDef(self.tr("&Before Commit"), self.saveOldRevision),
                ]),
                #ActionDef(plur("Save Revision^s As...", n), self.saveRevisionAs, QStyle.StandardPixmap.SP_DialogSaveButton),
                ActionDef(self.tr("Export As Patch..."), self.savePatchAs),
                None,
                ActionDef(self.tr("Open Containing &Folders", "", n), self.showInFolder, QStyle.StandardPixmap.SP_DirIcon),
                ActionDef(self.tr("&Copy Path(s)", "", n), self.copyPaths),
                ]

    def clear(self):
        super().clear()
        self.commitOid = None

    def setCommit(self, oid: pygit2.Oid):
        self.commitOid = oid

    def openNewRevision(self):
        self.openRevision(beforeCommit=False)

    def openOldRevision(self):
        self.openRevision(beforeCommit=True)

    def saveNewRevision(self):
        self.saveRevisionAs(beforeCommit=False)

    def saveOldRevision(self):
        self.saveRevisionAs(beforeCommit=True)

    def openRevision(self, beforeCommit: bool = False):
        errors = []

        for diff in self.confirmSelectedEntries(self.tr("Really open {0} files in external editor?")):
            try:
                name, blob, diffFile = self.getFileRevisionInfo(diff, beforeCommit)
            except FileNotFoundError as fnf:
                errors.append(fnf.filename + ": " + fnf.strerror)
                continue

            tempPath = os.path.join(getSessionTemporaryDirectory(), name)

            with open(tempPath, "wb") as f:
                f.write(blob.data)

            QDesktopServices.openUrl(QUrl.fromLocalFile(tempPath))

        if errors:
            QMessageBox.warning(self, self.tr("Open revision"), "\n\n".join(errors))

    def saveRevisionAs(self, beforeCommit: bool = False, saveInto=None):
        errors = []

        for diff in self.confirmSelectedEntries(self.tr("Really export {0} files?")):
            try:
                name, blob, diffFile = self.getFileRevisionInfo(diff, beforeCommit)
            except FileNotFoundError as fnf:
                errors.append(fnf.filename + ": " + fnf.strerror)
                continue

            if saveInto:
                savePath = os.path.join(saveInto, name)
            else:
                savePath, _ = PersistentFileDialog.getSaveFileName(self, self.tr("Save file revision as"), name)

            if not savePath:
                continue

            with open(savePath, "wb") as f:
                f.write(blob.data)

            os.chmod(savePath, diffFile.mode)

        if errors:
            QMessageBox.warning(self, self.tr("Save file revision as"), "\n\n".join(errors))

    def getFileRevisionInfo(self, diff: pygit2.Diff, beforeCommit: bool = False):
        if beforeCommit:
            diffFile = diff.delta.old_file
            if diff.delta.status == pygit2.GIT_DELTA_ADDED:
                raise FileNotFoundError(errno.ENOENT, self.tr("This file didn’t exist before the commit."), diffFile.path)
        else:
            diffFile = diff.delta.new_file
            if diff.delta.status == pygit2.GIT_DELTA_DELETED:
                raise FileNotFoundError(errno.ENOENT, self.tr("This file was deleted by the commit."), diffFile.path)

        blob: pygit2.Blob = self.repo[diffFile.id].peel(pygit2.Blob)

        atSuffix = shortHash(self.commitOid)
        if beforeCommit:
            atSuffix = F"before-{atSuffix}"

        name, ext = os.path.splitext(os.path.basename(diffFile.path))
        name = F"{name}@{atSuffix}{ext}"

        return name, blob, diffFile

    def openHeadRevision(self):
        errors = []

        for diff in self.confirmSelectedEntries(self.tr("Really open {0} files?")):
            diffFile = diff.delta.new_file
            if os.path.isfile(diffFile.path):
                QDesktopServices.openUrl(QUrl.fromLocalFile(diffFile.path))
            else:
                errors.append(f"{diffFile.path}: " + self.tr("There’s no file at this path on HEAD."))

        if errors:
            QMessageBox.warning(self, self.tr("Open revision at HEAD"), "\n\n".join(errors))
