from pathlib import Path
from typing import Callable, Generator

import pygit2

from gitfourchette import settings
from gitfourchette.exttools import openInTextEditor, openInDiffTool
from gitfourchette.filelists.filelistmodel import FileListModel, FILEPATH_ROLE
from gitfourchette.nav import NavLocator, NavContext
from gitfourchette.porcelain import BLANK_OID, isZeroId
from gitfourchette.qt import *
from gitfourchette.tempdir import getSessionTemporaryDirectory
from gitfourchette.toolbox import *


class SelectedFileBatchError(Exception):
    pass


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

        try:
            actions = self.createContextMenuActions(numIndexes)
        except Exception as exc:
            # Avoid exceptions in contextMenuEvent at all costs to prevent a crash
            # (endless loop of "This exception was delayed").
            excMessageBox(exc, message="Failed to create FileList context menu")
            return

        menu = ActionDef.makeQMenu(self, actions)
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

        diffDir = getSessionTemporaryDirectory()

        if self.navContext == NavContext.UNSTAGED:
            # Unstaged: compare indexed state to workdir file
            oldPath = dumpTempBlob(self.repo, diffDir, oldDiffFile, "INDEXED")
            newPath = os.path.join(self.repo.workdir, newDiffFile.path)
        elif self.navContext == NavContext.STAGED:
            # Staged: compare HEAD state to indexed state
            oldPath = dumpTempBlob(self.repo, diffDir, oldDiffFile, "HEAD")
            newPath = dumpTempBlob(self.repo, diffDir, newDiffFile, "STAGED")
        else:
            # Committed: compare parent state to this commit
            oldPath = dumpTempBlob(self.repo, diffDir, oldDiffFile, "OLD")
            newPath = dumpTempBlob(self.repo, diffDir, newDiffFile, "NEW")

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
        isLMB = bool(event.buttons() & Qt.MouseButton.LeftButton)
        isShift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        isCtrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)

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
                    "<br>".join(escape(f) for f in affectedPaths)))

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
            tempPath = dumpTempBlob(self.repo, getSessionTemporaryDirectory(), patch.delta.old_file, "HEAD")
            openInTextEditor(self, tempPath)

        self.confirmBatch(run, self.tr("Open HEAD version of file"),
                          self.tr("Really open <b>{0} files</b> in external editor?"))

    def wantPartialStash(self):
        paths = []
        for patch in self.selectedEntries():
            paths.append(patch.delta.old_file.path)
        self.stashFiles.emit(paths)

    def revertModeActionDef(self, n: int, callback: Callable):
        action = ActionDef(self.tr("Revert Old Mode(s)", "", n), callback, enabled=False)

        try:
            entries = self.selectedEntries()
        except ValueError:
            # If selectedEntries fails (e.g. due to stale diff), just return the default action
            return action

        for entry in entries:
            om = entry.delta.old_file.mode
            nm = entry.delta.new_file.mode
            if (entry.delta.status in [pygit2.GIT_DELTA_MODIFIED, pygit2.GIT_DELTA_RENAMED]
                    and om != nm
                    and nm in [pygit2.GIT_FILEMODE_BLOB, pygit2.GIT_FILEMODE_BLOB_EXECUTABLE]):
                action.enabled = True
                if n == 1:
                    if nm == pygit2.GIT_FILEMODE_BLOB_EXECUTABLE:
                        action.caption = self.tr("Revert Old Mode ({0})").format("-x")
                    elif nm == pygit2.GIT_FILEMODE_BLOB:
                        action.caption = self.tr("Revert Old Mode ({0})").format("+x")

        return action
