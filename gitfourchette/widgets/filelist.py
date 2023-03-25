from dataclasses import dataclass
from gitfourchette import log
from gitfourchette import settings
from gitfourchette.actiondef import ActionDef
from gitfourchette.globalshortcuts import GlobalShortcuts
from gitfourchette.nav import NavLocator, NavContext
from gitfourchette.qt import *
from gitfourchette.tempdir import getSessionTemporaryDirectory
from gitfourchette.util import (abbreviatePath, showInFolder, hasFlag, QSignalBlockerContext,
                                shortHash, PersistentFileDialog, showWarning, showInformation, askConfirmation,
                                paragraphs, isZeroId, openInTextEditor, openInDiffTool)
from pathlib import Path
from typing import Any, Callable, Generator
import errno
import html
import os
import pygit2


# If SVG icons don't show up, you may need to install the 'qt6-svg' package.
STATUS_ICONS = {}
for status in "ACDMRTUX":
    STATUS_ICONS[status] = QIcon(F"assets:status_{status.lower()}.svg")

FALLBACK_STATUS_ICON = QIcon("assets:status_fallback.svg")

PATCH_ROLE = Qt.ItemDataRole.UserRole + 0
FILEPATH_ROLE = Qt.ItemDataRole.UserRole + 1

BLANK_OID = pygit2.Oid(raw=b'')


def dumpTempDiffFile(repo: pygit2.Repository, diffFile: pygit2.DiffFile, inBrackets: str):
    blobId = diffFile.id
    blob: pygit2.Blob = repo[blobId].peel(pygit2.Blob)
    name, ext = os.path.splitext(os.path.basename(diffFile.path))
    name = F"{name}[{inBrackets}]{ext}"
    path = os.path.join(getSessionTemporaryDirectory(), name)
    with open(path, "wb") as f:
        f.write(blob.data)
    return path


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
        self.beginResetModel()

        self.entries.clear()
        self.fileRows.clear()

        for diff in diffs:
            for patchNo, delta in enumerate(diff.deltas):
                self.fileRows[delta.new_file.path] = len(self.entries)
                self.entries.append(FileListModel.Entry(delta, diff, patchNo))

        self.endResetModel()

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
        if role == PATCH_ROLE:
            return self.getPatchAt(index)

        elif role == FILEPATH_ROLE or role == Qt.ItemDataRole.DisplayRole:
            delta = self.getDeltaAt(index)
            if not delta:
                return "<NO DELTA>"

            path: str = self.getDeltaAt(index).new_file.path

            if role == Qt.ItemDataRole.DisplayRole:
                path = abbreviatePath(path, settings.prefs.pathDisplayStyle)

            return path

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
                opText = translate("FileList", "status:")

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
                    "<p style='white-space: pre'>"
                    F"<b>{opText} </b> {delta.status_char()} {opCap}"
                    F"\n<b>{fromText} </b> {html.escape(delta.old_file.path)} ({delta.old_file.mode:o})"
                    F"\n<b>{toText} </b> {html.escape(delta.new_file.path)} ({delta.new_file.mode:o})"
                )

        elif role == Qt.ItemDataRole.SizeHintRole:
            parentWidget: QWidget = self.parent()
            return QSize(-1, parentWidget.fontMetrics().height())

        return None

    def getRowForFile(self, path):
        return self.fileRows[path]

    def getFileAtRow(self, row: int):
        if row < 0 or row >= self.rowCount():
            return ""
        return self.data(self.index(row), FILEPATH_ROLE)

    def hasFile(self, path):
        return path in self.fileRows


class FileList(QListView):
    jump = Signal(NavLocator)
    nothingClicked = Signal()
    openDiffInNewWindow = Signal(pygit2.Patch, NavLocator)
    stashFiles = Signal(list)  # list[str]

    navContext: NavContext
    commitOid: pygit2.Oid

    def __init__(self, parent: QWidget, navContext: NavContext):
        super().__init__(parent)
        self.navContext = navContext
        self.commitOid = BLANK_OID
        self.setModel(FileListModel(self))
        self.repoWidget = parent
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        iconSize = self.fontMetrics().height()
        self.setIconSize(QSize(iconSize, iconSize))
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)  # prevent editing text after double-clicking
        self.setUniformItemSizes(True)  # potential perf boost with many files

    @property
    def flModel(self) -> FileListModel:
        return self.model()

    def isEmpty(self):
        return self.model().rowCount() == 0

    def setContents(self, diffs: list[pygit2.Diff]):
        self.flModel.setDiffs(diffs)

    def clear(self):
        self.flModel.clear()
        self.commitOid = BLANK_OID

    def contextMenuEvent(self, event: QContextMenuEvent):
        numIndexes = len(self.selectedIndexes())
        if numIndexes == 0:
            return

        menu = ActionDef.makeQMenu(self, self.createContextMenuActions(numIndexes))
        menu.setObjectName("FileListContextMenu")
        menu.exec(event.globalPos())

        # Can't set WA_DeleteOnClose because this crashes on macOS e.g. when exporting a patch.
        # (Context menu gets deleted while callback is running)
        # Qt docs say: "for the object to be deleted, the control must return to the event loop from which deleteLater()
        # was called" -- I suppose this means the context menu won't be deleted until the FileList has control again.
        menu.deleteLater()

    def createContextMenuActions(self, count) -> list[ActionDef]:
        return []

    def pathDisplayStyleSubmenu(self):
        def pdsAction(name: str, pds: settings.PathDisplayStyle):
            def setIt():
                settings.prefs.pathDisplayStyle = pds
            isCurrent = settings.prefs.pathDisplayStyle == pds
            return ActionDef(name, setIt, checkState=isCurrent)

        return ActionDef(
            translate("Prefs", "Path Display Style"),
            submenu=[
                pdsAction(translate("Prefs", "Full paths"), settings.PathDisplayStyle.FULL_PATHS),
                pdsAction(translate("Prefs", "Abbreviate directories"), settings.PathDisplayStyle.ABBREVIATE_DIRECTORIES),
                pdsAction(translate("Prefs", "Show filename only"), settings.PathDisplayStyle.SHOW_FILENAME_ONLY),
            ])

    def confirmBatch(self, callback: Callable[[pygit2.Patch], None], title: str, prompt: str, threshold: int = 3):
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

    def openWorkdirFile(self):
        def run(patch: pygit2.Patch):
            entryPath = os.path.join(self.repo.workdir, patch.delta.new_file.path)
            openInTextEditor(self, entryPath)

        self.confirmBatch(run, self.tr("Open in external editor"),
                          self.tr("Really open <b>{0} files</b> in external editor?"))

    def wantOpenInDiffTool(self):
        self.confirmBatch(self._openInDiffTool, self.tr("Open in external diff tool"),
                          self.tr("Really open <b>{0} files</b> in external diff tool?"))

    def _openInDiffTool(self, patch: pygit2.Patch):
        if isZeroId(patch.delta.new_file.id):
            raise SelectedFileBatchError(
                self.tr("{0}: Can’t open external diff tool on a deleted file.").format(patch.delta.new_file.path))

        if isZeroId(patch.delta.old_file.id):
            raise SelectedFileBatchError(
                self.tr("{0}: Can’t open external diff tool on a new file.").format(patch.delta.new_file.path))

        oldDiffFile = patch.delta.old_file
        newDiffFile = patch.delta.new_file

        if self.navContext == NavContext.UNSTAGED:
            # Unstaged: compare indexed state to workdir file
            oldPath = dumpTempDiffFile(self.repo, oldDiffFile, "INDEXED")
            newPath = os.path.join(self.repo.workdir, newDiffFile.path)
        elif self.navContext == NavContext.STAGED:
            # Staged: compare HEAD state to indexed state
            oldPath = dumpTempDiffFile(self.repo, oldDiffFile, "HEAD")
            newPath = dumpTempDiffFile(self.repo, newDiffFile, "STAGED")
        else:
            # Committed: compare parent state to this commit
            oldPath = dumpTempDiffFile(self.repo, oldDiffFile, "OLD")
            newPath = dumpTempDiffFile(self.repo, newDiffFile, "NEW")

        openInDiffTool(self, oldPath, newPath)

    def showInFolder(self):
        def run(entry: pygit2.Patch):
            path = os.path.join(self.repo.workdir, entry.delta.new_file.path)
            if not os.path.isfile(path):
                raise SelectedFileBatchError(self.tr("{0}: This file doesn’t exist at this path anymore.").format(entry.delta.new_file.path))
            showInFolder(path)

        self.confirmBatch(run, self.tr("Open paths"),
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
        if indexes:
            current = indexes[0]
        else:
            # Deselecting (e.g. with shift/ctrl) doesn't necessarily mean that the selection has been emptied.
            # Find an index that is still selected to keep the DiffView in sync with the selection.
            current = self.currentIndex()
            selectedIndexes = self.selectedIndexes()

            if current.isValid() and selectedIndexes:
                # currentIndex may be outside the selection, find the selected index that is closest to currentIndex.
                current = min(selectedIndexes, key=lambda index: abs(index.row() - current.row()))
            else:
                current = None

        if current and current.isValid():
            locator = self.getNavLocatorForIndex(current)
            self.jump.emit(locator)
        else:
            self.nothingClicked.emit()

    def getNavLocatorForIndex(self, index: QModelIndex):
        filePath = index.data(FILEPATH_ROLE)
        return NavLocator(self.navContext, self.commitOid, filePath)

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
            if not patch or not patch.delta:
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
        def warnBinary(affectedPaths):
            showWarning(
                self,
                self.tr("Save patch file"),
                paragraphs(
                    self.tr("For the time being, {0} is unable to export binary patches "
                            "from a selection of files.").format(qAppName()),
                    self.tr("The following binary files were skipped in the patch:"),
                    "<br>".join(html.escape(f) for f in affectedPaths)))

        entries = list(self.selectedEntries())

        names = set()

        skippedBinaryFiles = []

        bigpatch = b""
        for patch in entries:
            if patch.delta.status == pygit2.GIT_DELTA_DELETED:
                diffFile = patch.delta.old_file
            else:
                diffFile = patch.delta.new_file
            if patch.delta.is_binary:
                skippedBinaryFiles.append(diffFile.path)
                continue
            if patch.data:
                bigpatch += patch.data
                names.add(Path(diffFile.path).stem)

        if not bigpatch:
            if skippedBinaryFiles:
                warnBinary(skippedBinaryFiles)
            else:
                showInformation(self, self.tr("Save patch file"), self.tr("The patch is empty."))
            return

        name = ", ".join(sorted(names)) + ".patch"

        def dump(path):
            with open(path, "wb") as f:
                f.write(bigpatch)
            if skippedBinaryFiles:
                warnBinary(skippedBinaryFiles)

        if saveInto:
            savePath = os.path.join(saveInto, name)
            dump(savePath)
        else:
            qfd = PersistentFileDialog.saveFile(self, "SaveFile", self.tr("Save patch file"), name)
            qfd.fileSelected.connect(dump)
            qfd.show()

    def getFirstPath(self) -> str:
        model: FileListModel = self.model()
        index: QModelIndex = model.index(0)
        if index.isValid():
            return model.getPatchAt(index).delta.new_file.path
        else:
            return ""

    def selectFile(self, file: str):
        if not file:
            return False

        try:
            row = self.model().getRowForFile(file)
        except KeyError:
            return False

        if self.selectionModel().isRowSelected(row):
            # Re-selecting an already selected row may deselect it??
            return True

        self.selectRow(row)
        return True

    def getPatchForFile(self, file: str):
        try:
            row = self.flModel.getRowForFile(file)
            return self.flModel.getPatchAt(self.flModel.index(row, 0))
        except KeyError:
            return None

    def openHeadRevision(self):
        def run(patch: pygit2.Patch):
            tempPath = dumpTempDiffFile(self.repo, patch.delta.old_file, "HEAD")
            openInTextEditor(self, tempPath)

        self.confirmBatch(run, self.tr("Open HEAD version of file"),
                          self.tr("Really open <b>{0} files</b> in external editor?"))

    def wantPartialStash(self):
        paths = []
        for patch in self.selectedEntries():
            paths.append(patch.delta.old_file.path)
        self.stashFiles.emit(paths)


class DirtyFiles(FileList):
    stageFiles = Signal(list)
    discardFiles = Signal(list)

    def __init__(self, parent):
        super().__init__(parent, NavContext.UNSTAGED)

        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

    def createContextMenuActions(self, n):
        return [
            ActionDef(
                self.tr("&Stage %n File(s)", "", n),
                self.stage,
                QStyle.StandardPixmap.SP_ArrowDown,
                shortcuts=GlobalShortcuts.stageHotkeys,
            ),
            ActionDef(
                self.tr("&Discard Changes", "", n),
                self.discard,
                QStyle.StandardPixmap.SP_TrashIcon,
                shortcuts=GlobalShortcuts.discardHotkeys,
            ),
            ActionDef.SEPARATOR,
            ActionDef(self.tr("&Open in {0}", "", n).format(settings.getExternalEditorName()),
                      self.openWorkdirFile, icon=QStyle.StandardPixmap.SP_FileIcon),
            ActionDef(self.tr("Open &Diff in {0}", "", n).format(settings.getDiffToolName()),
                      self.wantOpenInDiffTool, icon=QStyle.StandardPixmap.SP_FileIcon),
            ActionDef(self.tr("E&xport As Patch..."), self.savePatchAs),
            ActionDef(self.tr("&Stash %n File(s)...", "", n), self.wantPartialStash),
            ActionDef.SEPARATOR,
            ActionDef(self.tr("Open &Path(s)", "", n), self.showInFolder, icon=QStyle.StandardPixmap.SP_DirIcon),
            ActionDef(self.tr("&Copy Path(s)", "", n), self.copyPaths),
            ActionDef.SEPARATOR,
            ActionDef(self.tr("Open HEAD Version(s) in {0}", "", n).format(settings.getExternalEditorName()),
                      self.openHeadRevision),
            ActionDef.SEPARATOR,
            self.pathDisplayStyleSubmenu()
        ]

    def keyPressEvent(self, event: QKeyEvent):
        k = event.key()
        if k in GlobalShortcuts.stageHotkeys:
            self.stage()
        elif k in GlobalShortcuts.discardHotkeys:
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
        super().__init__(parent, NavContext.STAGED)

        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

    def createContextMenuActions(self, n):
        return [
            ActionDef(
                self.tr("&Unstage %n File(s)", "", n),
                self.unstage,
                QStyle.StandardPixmap.SP_ArrowUp,
                shortcuts=GlobalShortcuts.discardHotkeys,
            ),
            ActionDef.SEPARATOR,
            ActionDef(self.tr("&Open in {0}", "", n).format(settings.getExternalEditorName()),
                      self.openWorkdirFile, QStyle.StandardPixmap.SP_FileIcon),
            ActionDef(self.tr("Open &Diff in {0}", "", n).format(settings.getDiffToolName()),
                      self.wantOpenInDiffTool, QStyle.StandardPixmap.SP_FileIcon),
            ActionDef(self.tr("E&xport As Patch..."), self.savePatchAs),
            ActionDef(self.tr("&Stash %n File(s)...", "", n), self.wantPartialStash),
            ActionDef.SEPARATOR,
            ActionDef(self.tr("Open &Path(s)", "", n), self.showInFolder, QStyle.StandardPixmap.SP_DirIcon),
            ActionDef(self.tr("&Copy Path(s)", "", n), self.copyPaths),
            ActionDef.SEPARATOR,
            ActionDef(self.tr("Open &HEAD Version(s) in {0}", "", n).format(settings.getExternalEditorName()),
                      self.openHeadRevision),
            ActionDef.SEPARATOR,
            self.pathDisplayStyleSubmenu()
        ] + super().createContextMenuActions(n)

    def keyPressEvent(self, event: QKeyEvent):
        k = event.key()
        if k in GlobalShortcuts.stageHotkeys + GlobalShortcuts.discardHotkeys:
            self.unstage()
        else:
            super().keyPressEvent(event)

    def unstage(self):
        self.unstageFiles.emit(list(self.selectedEntries()))


class CommittedFiles(FileList):
    def __init__(self, parent: QWidget):
        super().__init__(parent, NavContext.COMMITTED)

    def createContextMenuActions(self, n):
        return [
            ActionDef(self.tr("Open Diff in New &Window"), self.wantOpenDiffInNewWindow),
            ActionDef(self.tr("Open &Diff in {0}", "", n).format(settings.getDiffToolName()),
                      self.wantOpenInDiffTool, QStyle.StandardPixmap.SP_FileIcon),
            ActionDef(self.tr("&Open Revision(s)...", "", n), icon=QStyle.StandardPixmap.SP_FileIcon, submenu=
            [
                ActionDef(self.tr("&At Commit"), self.openNewRevision),
                ActionDef(self.tr("&Before Commit"), self.openOldRevision),
                ActionDef.SEPARATOR,
                ActionDef(self.tr("&Current (working directory)"), self.openHeadRevision),
            ]),
            ActionDef(self.tr("&Save Revision(s)...", "", n), icon=QStyle.StandardPixmap.SP_DialogSaveButton, submenu=
            [
                ActionDef(self.tr("&At Commit"), self.saveNewRevision),
                ActionDef(self.tr("&Before Commit"), self.saveOldRevision),
            ]),
            #ActionDef(plur("Save Revision^s As...", n), self.saveRevisionAs, QStyle.StandardPixmap.SP_DialogSaveButton),
            ActionDef(self.tr("E&xport As Patch..."), self.savePatchAs),
            ActionDef.SEPARATOR,
            ActionDef(self.tr("Open &Path(s)", "", n), self.showInFolder, QStyle.StandardPixmap.SP_DirIcon),
            ActionDef(self.tr("&Copy Path(s)", "", n), self.copyPaths),
            ActionDef.SEPARATOR,
            self.pathDisplayStyleSubmenu()
        ]

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

    def saveRevisionAsTempFile(self, diff, beforeCommit: bool = False):
        try:
            name, blob, diffFile = self.getFileRevisionInfo(diff, beforeCommit)
        except FileNotFoundError as fnf:
            raise SelectedFileBatchError(fnf.filename + ": " + fnf.strerror)

        tempPath = os.path.join(getSessionTemporaryDirectory(), name)

        with open(tempPath, "wb") as f:
            f.write(blob.data)

        return tempPath

    def openRevision(self, beforeCommit: bool = False):
        def run(patch: pygit2.Patch):
            tempPath = self.saveRevisionAsTempFile(patch, beforeCommit)
            openInTextEditor(self, tempPath)

        if beforeCommit:
            title = self.tr("Open revision before commit")
        else:
            title = self.tr("Open revision at commit")

        self.confirmBatch(run, title,
                          self.tr("Really open <b>{0} files</b> in external editor?"))

    def saveRevisionAs(self, beforeCommit: bool = False, saveInto: str = ""):
        def dump(path: str, mode: int, data: bytes):
            with open(path, "wb") as f:
                f.write(data)
            os.chmod(path, mode)

        def run(diff):
            try:
                name, blob, diffFile = self.getFileRevisionInfo(diff, beforeCommit)
            except FileNotFoundError as fnf:
                raise SelectedFileBatchError(fnf.filename + ": " + fnf.strerror)

            if saveInto:
                path = os.path.join(saveInto, name)
                dump(path, diffFile.mode, blob.data)
            else:
                qfd = PersistentFileDialog.saveFile(
                    self, "SaveFile", self.tr("Save file revision as"), name)
                qfd.fileSelected.connect(lambda path: dump(path, diffFile.mode, blob.data))
                qfd.show()

        if beforeCommit:
            title = self.tr("Save revision before commit")
        else:
            title = self.tr("Save revision at commit")

        self.confirmBatch(run, title, self.tr("Really export <b>{0} files</b>?"))

    def getFileRevisionInfo(self, patch: pygit2.Patch, beforeCommit: bool = False) -> tuple[str, pygit2.Blob, pygit2.DiffFile]:
        if beforeCommit:
            diffFile = patch.delta.old_file
            if patch.delta.status == pygit2.GIT_DELTA_ADDED:
                raise FileNotFoundError(errno.ENOENT, self.tr("This file didn’t exist before the commit."), diffFile.path)
        else:
            diffFile = patch.delta.new_file
            if patch.delta.status == pygit2.GIT_DELTA_DELETED:
                raise FileNotFoundError(errno.ENOENT, self.tr("This file was deleted by the commit."), diffFile.path)

        blob: pygit2.Blob = self.repo[diffFile.id].peel(pygit2.Blob)

        atSuffix = shortHash(self.commitOid)
        if beforeCommit:
            atSuffix = F"before-{atSuffix}"

        name, ext = os.path.splitext(os.path.basename(diffFile.path))
        name = F"{name}@{atSuffix}{ext}"

        return name, blob, diffFile

    def openHeadRevision(self):
        def run(patch: pygit2.Patch):
            diffFile = patch.delta.new_file
            path = os.path.join(self.repo.workdir, diffFile.path)
            if os.path.isfile(path):
                openInTextEditor(self, path)
            else:
                raise SelectedFileBatchError(self.tr("{0}: There’s no file at this path on HEAD.").format(diffFile.path))

        self.confirmBatch(run, self.tr("Open revision at HEAD"), self.tr("Really open <b>{0} files</b>?"))

    def wantOpenDiffInNewWindow(self):
        def run(patch: pygit2.Patch):
            self.openDiffInNewWindow.emit(patch, NavLocator(self.navContext, self.commitOid, patch.delta.new_file.path))

        self.confirmBatch(run, self.tr("Open diff in new window"), self.tr("Really open <b>{0} files</b>?"))
