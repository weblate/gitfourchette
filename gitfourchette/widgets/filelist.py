from dataclasses import dataclass
from gitfourchette import log
from gitfourchette import settings
from gitfourchette.qt import *
from gitfourchette.stagingstate import StagingState
from gitfourchette.tempdir import getSessionTemporaryDirectory
from gitfourchette.util import (abbreviatePath, showInFolder, hasFlag, ActionDef, quickMenu, QSignalBlockerContext,
                                shortHash, PersistentFileDialog, showWarning, askConfirmation)
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


class SelectedFileBatchError(Exception):
    pass


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
                    "<b>" + translate("FileList", "untracked file") + "</b><br>" +
                    F"{html.escape(delta.new_file.path)} ({delta.new_file.mode:o})"
                )
            elif delta.status == pygit2.GIT_DELTA_CONFLICTED:
                conflictedText = translate("FileList", "merge conflict")

                return (
                    f"<b>{conflictedText}</b><br>"
                )
            else:
                fromText = translate("FileList", "from:")
                toText = translate("FileList", "to:")
                opText = translate("FileList", "operation:")

                # see git_diff_status_char (diff_print.c)
                operationCaptions = {
                    "A": translate("FileList", "(added)"),
                    "C": translate("FileList", "(copied)"),
                    "D": translate("FileList", "(deleted)"),
                    "I": translate("FileList", "(ignored)"),
                    "M": translate("FileList", "(modified)"),
                    "R": translate("FileList", "(renamed, {0}% similarity)"),
                    "T": translate("FileList", "(file type changed)"),
                    "U": translate("FileList", "(updated but unmerged)"),
                    "X": translate("FileList", "(unreadable)"),
                    "?": translate("FileList", "(untracked)"),
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
        menu.exec(event.globalPos())

        # Can't set WA_DeleteOnClose because this crashes on macOS e.g. when exporting a patch.
        # (Context menu gets deleted while callback is running)
        # Qt docs say: "for the object to be deleted, the control must return to the event loop from which deleteLater()
        # was called" -- I suppose this means the context menu won't be deleted until the FileList has control again.
        menu.deleteLater()

    def createContextMenuActions(self, count):
        return []

    def confirmBatch(self, callback, title: str, prompt: str, threshold: int = 3):
        entries = list(self.selectedEntries())

        def runBatch():
            errors = []

            for e in entries:
                try:
                    callback(e)
                except SelectedFileBatchError as exc:
                    errors.append(str(exc))

            if errors:
                showWarning(self, title, "<br>".join(errors))

        if len(entries) <= threshold:
            runBatch()
        else:
            numFiles = len(entries)

            qmb = askConfirmation(
                self,
                title,
                prompt.format(numFiles),
                runBatch,
                QMessageBox.StandardButton.YesAll | QMessageBox.StandardButton.Cancel,
                show=False)

            qmb.button(QMessageBox.StandardButton.YesAll).clicked.connect(runBatch)
            qmb.show()

    def openFile(self):
        def run(entry: pygit2.Patch):
            entryPath = os.path.join(self.repo.workdir, entry.delta.new_file.path)
            QDesktopServices.openUrl(QUrl.fromLocalFile(entryPath))

        self.confirmBatch(run, self.tr("Open in external editor"),
                          self.tr("Really open <b>{0} files</b> in external editor?"))

    def showInFolder(self):
        def run(entry: pygit2.Patch):
            showInFolder(os.path.join(self.repo.workdir, entry.delta.new_file.path))

        self.confirmBatch(run, self.tr("Open containing folder"),
                          self.tr("Really open <b>{0} folders</b>?"))

    def keyPressEvent(self, event: QKeyEvent):
        # The default keyPressEvent copies the displayed label of the selected items.
        # We want to copy the full path of the selected items instead.
        if event.matches(QKeySequence.StandardKey.Copy):
            self.copyPaths()
        else:
            super().keyPressEvent(event)

    def copyPaths(self):
        wd = self.repo.workdir
        text = '\n'.join(os.path.join(wd, entry.delta.new_file.path)
                         for entry in self.selectedEntries())
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
        def run(diff):
            diffFile: pygit2.DiffFile = diff.delta.old_file

            blob: pygit2.Blob = self.repo[diffFile.id].peel(pygit2.Blob)

            name, ext = os.path.splitext(os.path.basename(diffFile.path))
            name = F"{name}[lastcommit]{ext}"

            tempPath = os.path.join(getSessionTemporaryDirectory(), name)

            with open(tempPath, "wb") as f:
                f.write(blob.data)

            QDesktopServices.openUrl(QUrl.fromLocalFile(tempPath))

        self.confirmBatch(run, self.tr("Open unmodified revision"),
                          self.tr("Really open <b>{0} files</b> in external editor?"))


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
        def run(diff):
            try:
                name, blob, diffFile = self.getFileRevisionInfo(diff, beforeCommit)
            except FileNotFoundError as fnf:
                raise SelectedFileBatchError(fnf.filename + ": " + fnf.strerror)

            tempPath = os.path.join(getSessionTemporaryDirectory(), name)

            with open(tempPath, "wb") as f:
                f.write(blob.data)

            QDesktopServices.openUrl(QUrl.fromLocalFile(tempPath))

        if beforeCommit:
            title = self.tr("Open revision before commit")
        else:
            title = self.tr("Open revision at commit")

        self.confirmBatch(run, title,
                          self.tr("Really open <b>{0} files</b> in external editor?"))

    def saveRevisionAs(self, beforeCommit: bool = False, saveInto=None):
        def run(diff):
            try:
                name, blob, diffFile = self.getFileRevisionInfo(diff, beforeCommit)
            except FileNotFoundError as fnf:
                raise SelectedFileBatchError(fnf.filename + ": " + fnf.strerror)

            if saveInto:
                savePath = os.path.join(saveInto, name)
            else:
                savePath, _ = PersistentFileDialog.getSaveFileName(self, self.tr("Save file revision as"), name)

            if savePath:
                with open(savePath, "wb") as f:
                    f.write(blob.data)
                os.chmod(savePath, diffFile.mode)

        if beforeCommit:
            title = self.tr("Save revision before commit")
        else:
            title = self.tr("Save revision at commit")

        self.confirmBatch(run, title, self.tr("Really export <b>{0} files</b>?"))

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
        def run(diff):
            diffFile = diff.delta.new_file
            path = os.path.join(self.repo.workdir, diffFile.path)
            if os.path.isfile(path):
                QDesktopServices.openUrl(QUrl.fromLocalFile(path))
            else:
                raise SelectedFileBatchError(self.tr("{0}: There’s no file at this path on HEAD.").format(diffFile.path))

        self.confirmBatch(run, self.tr("Open revision at HEAD"), self.tr("Really open <b>{0} files</b>?"))
