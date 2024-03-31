import os
from contextlib import suppress
from pathlib import Path
from typing import Callable, Generator

from gitfourchette import settings
from gitfourchette.exttools import openInTextEditor, openInDiffTool
from gitfourchette.filelists.filelistmodel import FileListModel, FILEPATH_ROLE, PATCH_ROLE
from gitfourchette.forms.searchbar import SearchBar
from gitfourchette.globalshortcuts import GlobalShortcuts
from gitfourchette.nav import NavLocator, NavContext, NavFlags
from gitfourchette.porcelain import *
from gitfourchette.qt import *
from gitfourchette.tasks import *
from gitfourchette.tempdir import getSessionTemporaryDirectory
from gitfourchette.toolbox import *
from gitfourchette.trtables import TrTables


class SelectedFileBatchError(Exception):
    pass


class FileListDelegate(QStyledItemDelegate):
    """
    Item delegate for QListView that supports highlighting search terms from a SearchBar
    """

    def searchTerm(self, option: QStyleOptionViewItem):
        searchBar: SearchBar = option.widget.searchBar
        return searchBar.searchTerm if searchBar.isVisible() else ""

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        hasFocus = option.state & QStyle.StateFlag.State_HasFocus
        isSelected = option.state & QStyle.StateFlag.State_Selected
        style = option.widget.style()
        colorGroup = QPalette.ColorGroup.Normal if hasFocus else QPalette.ColorGroup.Inactive
        searchTerm = self.searchTerm(option)

        painter.save()

        # Prepare icon and text rects
        icon: QIcon = index.data(Qt.ItemDataRole.DecorationRole)
        if icon is not None and not icon.isNull():
            iconRect = QRect(option.rect.topLeft() + QPoint(2, 0), option.decorationSize)
        else:
            iconRect = QRect()

        textRect = QRect(option.rect)
        textRect.setLeft(iconRect.right() + 4)
        textRect.setRight(textRect.right() - 2)

        # Set highlighted text color if this item is selected
        if isSelected:
            painter.setPen(option.palette.color(colorGroup, QPalette.ColorRole.HighlightedText))

        # Draw default background
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, option, painter, option.widget)

        # Draw focus rect (necessary with Breeze/Plasma 6)
        if hasFocus:
            o2 = QStyleOptionViewItem(option)
            o2.rect = textRect
            style.drawPrimitive(QStyle.PrimitiveElement.PE_FrameFocusRect, o2, painter, option.widget)

        # Draw icon
        if not iconRect.isEmpty():
            icon.paint(painter, iconRect, option.decorationAlignment)

        # Draw text
        font: QFont = index.data(Qt.ItemDataRole.FontRole)
        if font:
            painter.setFont(font)
        fullText = index.data(Qt.ItemDataRole.DisplayRole)
        text = painter.fontMetrics().elidedText(fullText, option.textElideMode, textRect.width())
        painter.drawText(textRect, option.displayAlignment, text)

        # Highlight search term
        if searchTerm and searchTerm in fullText.lower():
            needlePos = text.lower().find(searchTerm)
            if needlePos < 0:
                needlePos = text.find("\u2026")  # unicode ellipsis character (...)
                needleLen = 1
            else:
                needleLen = len(searchTerm)

            SearchBar.highlightNeedle(painter, textRect, text, needlePos, needleLen)

        painter.restore()


class FileList(QListView):
    nothingClicked = Signal()
    selectedCountChanged = Signal(int)
    openDiffInNewWindow = Signal(Patch, NavLocator)
    openSubRepo = Signal(str)
    statusMessage = Signal(str)

    navContext: NavContext
    """ 
    COMMITTED, STAGED or DIRTY.
    Does not change throughout the lifespan of this FileList.
    """

    commitOid: Oid
    """
    The commit that is currently being shown.
    Only valid if navContext == COMMITTED.
    """

    skippedRenameDetection: bool
    """
    In large diffs, we skip rename detection.
    """

    def __init__(self, parent: QWidget, navContext: NavContext):
        super().__init__(parent)

        flModel = FileListModel(self, navContext)
        self.setModel(flModel)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

        self.navContext = navContext
        self.commitOid = NULL_OID
        self.skippedRenameDetection = False
        self._selectionBackup = None

        self.repoWidget = parent
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        iconSize = self.fontMetrics().height()
        self.setIconSize(QSize(iconSize, iconSize))
        self.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)  # prevent editing text after double-clicking
        self.setUniformItemSizes(True)  # potential perf boost with many files

        self.searchBar = SearchBar(self, self.tr("Find a file by pathFind file"))
        self.searchBar.setUpItemViewBuddy()
        self.searchBar.ui.forwardButton.hide()
        self.searchBar.ui.backwardButton.hide()
        self.searchBar.hide()

        # Search result highlighter
        self.setItemDelegate(FileListDelegate(self))

        self.refreshPrefs()

    def refreshPrefs(self):
        self.setVerticalScrollMode(settings.prefs.listViewScrollMode)

    @property
    def flModel(self) -> FileListModel:
        return self.model()

    def isEmpty(self):
        return self.model().rowCount() == 0

    def setContents(self, diffs: list[Diff], skippedRenameDetection: bool):
        self.flModel.setDiffs(diffs)
        self.skippedRenameDetection = skippedRenameDetection

    def clear(self):
        self.flModel.clear()
        self.commitOid = NULL_OID
        self.skippedRenameDetection = False

    def makeContextMenu(self):
        patches = list(self.selectedPatches())
        if len(patches) == 0:
            return None

        actions = self.createContextMenuActions(patches)
        menu = ActionDef.makeQMenu(self, actions)
        menu.setObjectName("FileListContextMenu")
        return menu

    def contextMenuEvent(self, event: QContextMenuEvent):
        try:
            menu = self.makeContextMenu()
        except Exception as exc:
            # Avoid exceptions in contextMenuEvent at all costs to prevent a crash
            # (endless loop of "This exception was delayed").
            excMessageBox(exc, message="Failed to create FileList context menu")
            return

        if not menu:
            return

        menu.exec(event.globalPos())

        # Can't set WA_DeleteOnClose because this crashes on macOS e.g. when exporting a patch.
        # (Context menu gets deleted while callback is running)
        # Qt docs say: "for the object to be deleted, the control must return to the event loop from which deleteLater()
        # was called" -- I suppose this means the context menu won't be deleted until the FileList has control again.
        menu.deleteLater()

    def createContextMenuActions(self, patches: list[Patch]) -> list[ActionDef]:
        """ To be overridden """

        def pathDisplayStyleAction(pds: PathDisplayStyle):
            def setIt():
                settings.prefs.pathDisplayStyle = pds
            isCurrent = settings.prefs.pathDisplayStyle == pds
            name = TrTables.prefKey(pds.name)
            return ActionDef(name, setIt, checkState=isCurrent)

        n = len(patches)

        return [
            ActionDef.SEPARATOR,

            ActionDef(
                self.tr("Open &Folder(s)", "", n),
                self.showInFolder,
                QStyle.StandardPixmap.SP_DirIcon,
            ),

            ActionDef(
                self.tr("&Copy Path(s)", "", n),
                self.copyPaths,
                shortcuts=GlobalShortcuts.copy,
            ),

            ActionDef(
                TrTables.prefKey("pathDisplayStyle"),
                submenu=[pathDisplayStyleAction(style) for style in PathDisplayStyle],
            ),
        ]

    def confirmBatch(self, callback: Callable[[Patch], None], title: str, prompt: str, threshold: int = 3):
        patches = list(self.selectedPatches())

        def runBatch():
            errors = []

            for patch in patches:
                try:
                    callback(patch)
                except SelectedFileBatchError as exc:
                    errors.append(str(exc))

            if errors:
                showWarning(self, title, "<br>".join(errors))

        if len(patches) <= threshold:
            runBatch()
        else:
            numFiles = len(patches)

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
        def run(patch: Patch):
            entryPath = os.path.join(self.repo.workdir, patch.delta.new_file.path)
            openInTextEditor(self, entryPath)

        self.confirmBatch(run, self.tr("Open in external editor"),
                          self.tr("Really open <b>{0} files</b> in external editor?"))

    def wantOpenInDiffTool(self):
        self.confirmBatch(self._openInDiffTool, self.tr("Open in external diff tool"),
                          self.tr("Really open <b>{0} files</b> in external diff tool?"))

    def _openInDiffTool(self, patch: Patch):
        if patch.delta.new_file.id == NULL_OID:
            raise SelectedFileBatchError(
                self.tr("{0}: Can’t open external diff tool on a deleted file.").format(patch.delta.new_file.path))

        if patch.delta.old_file.id == NULL_OID:
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
        def run(entry: Patch):
            path = os.path.join(self.repo.workdir, entry.delta.new_file.path)
            path = os.path.normpath(path)  # get rid of any trailing slashes (submodules)
            if not os.path.exists(path):  # check exists, not isfile, for submodules
                raise SelectedFileBatchError(self.tr("{0}: This file doesn’t exist at this path anymore.").format(entry.delta.new_file.path))
            showInFolder(path)

        self.confirmBatch(run, self.tr("Open paths"),
                          self.tr("Really open <b>{0} folders</b>?"))

    def keyPressEvent(self, event: QKeyEvent):
        # The default keyPressEvent copies the displayed label of the selected items.
        # We want to copy the full path of the selected items instead.
        if event.matches(QKeySequence.StandardKey.Copy):
            self.copyPaths()
        elif event.key() == Qt.Key.Key_Escape:
            if self.searchBar.isVisible():  # close search bar if it doesn't have focus
                self.searchBar.hide()
            else:
                QApplication.beep()
        else:
            super().keyPressEvent(event)

    def copyPaths(self):
        text = '\n'.join(self.repo.in_workdir(path) for path in self.selectedPaths())
        if not text:
            return

        QApplication.clipboard().setText(text)
        self.statusMessage.emit(clipboardStatusMessage(text))

    def selectRow(self, rowNumber=0):
        if self.model().rowCount() == 0:
            self.nothingClicked.emit()
            self.clearSelection()
        else:
            self.setCurrentIndex(self.model().index(rowNumber or 0, 0))

    def selectionChanged(self, justSelected: QItemSelection, justDeselected: QItemSelection):
        super().selectionChanged(justSelected, justDeselected)

        selectedIndexes = self.selectedIndexes()
        numSelectedTotal = len(selectedIndexes)

        justSelectedIndexes = list(justSelected.indexes())
        if justSelectedIndexes:
            current = justSelectedIndexes[0]
        else:
            # Deselecting (e.g. with shift/ctrl) doesn't necessarily mean that the selection has been emptied.
            # Find an index that is still selected to keep the DiffView in sync with the selection.
            current = self.currentIndex()

            if current.isValid() and selectedIndexes:
                # currentIndex may be outside the selection, find the selected index that is closest to currentIndex.
                current = min(selectedIndexes, key=lambda index: abs(index.row() - current.row()))
            else:
                current = None

        self.selectedCountChanged.emit(numSelectedTotal)

        # We're the active FileList, clear counterpart.
        self._setCounterpart(-1)

        if current and current.isValid():
            locator = self.getNavLocatorForIndex(current)
            locator = locator.withExtraFlags(NavFlags.AllowMultiSelect)
            Jump.invoke(self, locator)
        else:
            self.nothingClicked.emit()

    def highlightCounterpart(self, loc: NavLocator):
        try:
            row = self.flModel.getRowForFile(loc.path)
        except KeyError:
            row = -1
        self._setCounterpart(row)

    def _setCounterpart(self, newRow: int):
        model = self.flModel
        oldRow = model.highlightedCounterpartRow

        if oldRow == newRow:
            return

        model.highlightedCounterpartRow = newRow

        if oldRow >= 0:
            oldIndex = model.index(oldRow, 0)
            self.update(oldIndex)

        if newRow >= 0:
            newIndex = model.index(newRow, 0)
            self.selectionModel().setCurrentIndex(newIndex, QItemSelectionModel.SelectionFlag.NoUpdate)
            self.update(newIndex)

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

    def selectedPatches(self) -> Generator[Patch, None, None]:
        index: QModelIndex
        for index in self.selectedIndexes():
            patch: Patch = index.data(PATCH_ROLE)
            if not patch or not patch.delta:
                raise ValueError(self.tr("This file appears to have changed since we last read it. Try refreshing the window."))
            assert isinstance(patch, Patch)
            yield patch

    def selectedPaths(self) -> Generator[str, None, None]:
        index: QModelIndex
        for index in self.selectedIndexes():
            path: str = index.data(FILEPATH_ROLE)
            if not path:
                continue
            yield path

    @property
    def repo(self) -> Repo:
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
            message = paragraphs(
                self.tr("For the time being, {0} is unable to export binary patches from a selection of files."),
                self.tr("The following binary files were skipped in the patch:")).format(qAppName())
            message += ulList(escape(f) for f in affectedPaths)
            showWarning(self, self.tr("Save patch file"), message)

        patches = list(self.selectedPatches())
        names = set()
        skippedBinaryFiles = []

        bigpatch = b""
        for patch in patches:
            if patch.delta.status == DeltaStatus.DELETED:
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

    def firstPath(self) -> str:
        index: QModelIndex = self.flModel.index(0)
        if index.isValid():
            return index.data(FILEPATH_ROLE)
        else:
            return ""

    def paths(self) -> Generator[str, None, None]:
        flModel = self.flModel
        for row in range(flModel.rowCount()):
            index = flModel.index(row)
            yield index.data(FILEPATH_ROLE)

    def selectFile(self, file: str) -> bool:
        if not file:
            return False

        try:
            row = self.flModel.getRowForFile(file)
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
        def run(patch: Patch):
            tempPath = dumpTempBlob(self.repo, getSessionTemporaryDirectory(), patch.delta.old_file, "HEAD")
            openInTextEditor(self, tempPath)

        self.confirmBatch(run, self.tr("Open HEAD version of file"),
                          self.tr("Really open <b>{0} files</b> in external editor?"))

    def wantPartialStash(self):
        paths = [patch.delta.old_file.path for patch in self.selectedPatches()]
        NewStash.invoke(self, paths)

    def openSubmoduleTabs(self):
        patches = list(p for p in self.selectedPatches() if p.delta.new_file.mode in [FileMode.COMMIT])
        for patch in patches:
            self.openSubRepo.emit(patch.delta.new_file.path)

    def revertModeActionDef(self, n: int, callback: Callable):
        action = ActionDef(self.tr("Revert Mode Change", "", n), callback, enabled=False)

        try:
            patches = self.selectedPatches()
        except ValueError:
            # If selectedPatches fails (e.g. due to stale diff), just return the default action
            return action

        for patch in patches:
            om = patch.delta.old_file.mode
            nm = patch.delta.new_file.mode
            if (patch.delta.status in [DeltaStatus.MODIFIED, DeltaStatus.RENAMED]
                    and om != nm
                    and nm in [FileMode.BLOB, FileMode.BLOB_EXECUTABLE]):
                action.enabled = True
                if n == 1:
                    if nm == FileMode.BLOB_EXECUTABLE:
                        action.caption = self.tr("Revert Mode to Non-Executable")
                    elif nm == FileMode.BLOB:
                        action.caption = self.tr("Revert Mode to Executable")

        return action

    def searchRange(self, searchRange: range) -> QModelIndex | None:
        # print("Search range:", searchRange)
        model = self.model()  # to filter out hidden rows, don't use self.clModel directly

        term = self.searchBar.searchTerm
        assert term
        assert term == term.lower(), "search term should have been sanitized"

        for i in searchRange:
            index = model.index(i, 0)
            path = model.data(index, FILEPATH_ROLE)
            if path and term in path.lower():
                return index

    def backUpSelection(self):
        oldSelected = list(self.selectedPaths())
        self._selectionBackup = oldSelected

    def clearSelectionBackup(self):
        self._selectionBackup = None

    def restoreSelectionBackup(self):
        if self._selectionBackup is None:
            return False

        paths = self._selectionBackup
        self._selectionBackup = None

        currentIndex: QModelIndex = self.currentIndex()
        cPath = currentIndex.data(FILEPATH_ROLE)

        if cPath not in paths:
            # Don't attempt to restore if we've jumped to another file
            return False

        if len(paths) == 1 and paths[0] == cPath:
            # Don't bother if the one file that we've selected is still the current one
            return False

        flModel = self.flModel
        selectionModel = self.selectionModel()
        SF = QItemSelectionModel.SelectionFlag

        with QSignalBlockerContext(self):
            # If we directly manipulate the QItemSelectionModel by calling .select() row-by-row,
            # then shift-selection may act counter-intuitively if the selection was discontiguous.
            # Preparing a QItemSelection upfront mitigates the strange shift-select behavior.
            newItemSelection = QItemSelection()
            for path in paths:
                with suppress(KeyError):
                    row = flModel.fileRows[path]
                    index = flModel.index(row, 0)
                    newItemSelection.select(index, index)
            selectionModel.clearSelection()
            selectionModel.select(newItemSelection, SF.Rows | SF.Select)
            selectionModel.setCurrentIndex(currentIndex, SF.Rows | SF.Current)

        return True
