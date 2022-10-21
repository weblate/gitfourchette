from gitfourchette import porcelain
from gitfourchette import settings
from gitfourchette.navhistory import NavPos
from gitfourchette.qt import *
from gitfourchette.stagingstate import StagingState
from gitfourchette.subpatch import extractSubpatch
from gitfourchette.trash import Trash
from gitfourchette.util import PersistentFileDialog, excMessageBox, ActionDef, quickMenu
from gitfourchette.widgets.diffmodel import DiffModel, LineData
from bisect import bisect_left, bisect_right
from pygit2 import GitError, Patch, Repository, Diff
import enum
import os
import pygit2
import sys


def get1FileChangedByDiff(diff: Diff):
    for p in diff:
        if p.delta.status != pygit2.GIT_DELTA_DELETED:
            return p.delta.new_file.path
    return ""


@enum.unique
class PatchPurpose(enum.IntEnum):
    STAGE = enum.auto()
    UNSTAGE = enum.auto()
    DISCARD = enum.auto()


class DiffGutter(QWidget):
    diffView: 'DiffView'

    def __init__(self, parent):
        super().__init__(parent)
        self.diffView = parent

        if sys.platform in ['darwin', 'win32']:
            dpr = 4
        else:
            dpr = 1  # On Linux, Qt doesn't seem to support cursors at non-1 DPR
        pix = QPixmap(f"assets:right_ptr@{dpr}x")
        pix.setDevicePixelRatio(dpr)
        flippedCursor = QCursor(pix, hotX=19, hotY=5)
        self.setCursor(flippedCursor)

    def sizeHint(self) -> QSize:
        return QSize(self.diffView.gutterWidth(), 0)

    def paintEvent(self, event: QPaintEvent):
        self.diffView.gutterPaintEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self.diffView.selectWholeLinesTo(event.pos())
            else:
                self.diffView.selectWholeLineAt(event.pos())

    def mouseMoveEvent(self, event: QMouseEvent):
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.diffView.selectWholeLinesTo(event.pos())


class DiffView(QPlainTextEdit):
    patchApplied: Signal = Signal(NavPos)

    lineData: list[LineData]
    lineCursorStartCache: list[int]
    lineHunkIDCache: list[int]
    currentStagingState: StagingState
    currentPatch: Patch
    repo: Repository

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setReadOnly(True)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)

        # First-time init so callbacks don't crash looking for missing attributes
        self.lineData = []
        self.lineCursorStartCache = []
        self.lineHunkIDCache = []
        self.currentStagingState = None
        self.currentPatch = None
        self.repo = None

        self.gutterMaxDigits = 0

        self.gutter = DiffGutter(self)
        self.updateRequest.connect(self.updateGutter)
        self.blockCountChanged.connect(self.updateGutterWidth)
        # self.cursorPositionChanged.connect(self.highlightCurrentLine)
        self.updateGutterWidth(0)

    def replaceDocument(self, repo: Repository, patch: Patch, stagingState: StagingState, dm: DiffModel):
        oldDocument = self.document()
        if oldDocument:
            oldDocument.deleteLater()  # avoid leaking memory/objects, even though we do set QTextDocument's parent to this QTextEdit

        self.currentStagingState = stagingState
        self.repo = repo
        self.currentPatch = patch

        self.setFont(dm.document.defaultFont())
        self.setDocument(dm.document)

        self.lineData = dm.lineData
        self.lineCursorStartCache = [ld.cursorStart for ld in self.lineData]
        self.lineHunkIDCache = [ld.hunkPos.hunkID for ld in self.lineData]

        tabWidth = settings.prefs.diff_tabSpaces

        # now reset defaults that are lost when changing documents
        self.setTabStopDistance(QFontMetricsF(dm.document.defaultFont()).horizontalAdvance(' ' * tabWidth))
        self.refreshWordWrap()
        self.setCursorWidth(2)

        if self.currentPatch and len(self.currentPatch.hunks) > 0:
            lastHunk = self.currentPatch.hunks[-1]
            maxNewLine = lastHunk.new_start + lastHunk.new_lines
            maxOldLine = lastHunk.old_start + lastHunk.old_lines
            self.gutterMaxDigits = len(str(max(maxNewLine, maxOldLine)))
        else:
            self.gutterMaxDigits = 0
        self.updateGutterWidth(0)

    def refreshWordWrap(self):
        if settings.prefs.diff_wordWrap:
            self.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        else:
            self.setWordWrapMode(QTextOption.WrapMode.NoWrap)

    def contextMenuEvent(self, event: QContextMenuEvent):
        # Get position of click in document
        clickedPosition = self.cursorForPosition(event.pos()).position()

        cursor: QTextCursor = self.textCursor()
        hasSelection = cursor.hasSelection()

        # Find hunk at click position
        clickedHunkID = self.findHunkIDAt(clickedPosition)

        menu: QMenu = self.createStandardContextMenu()

        actions = []

        if self.currentStagingState == None:
            actions = []

        elif self.currentStagingState == StagingState.COMMITTED:
            if hasSelection:
                actions = [
                    ActionDef("Export Lines as Patch...", self.exportSelection),
                    ActionDef("Revert Lines...", self.revertSelection),
                ]
            else:
                actions = [
                    ActionDef("Export Hunk as Patch...", lambda: self.exportHunk(clickedHunkID)),
                    ActionDef("Revert Hunk...", lambda: self.revertHunk(clickedHunkID)),
                ]

        elif self.currentStagingState == StagingState.UNTRACKED:
            if hasSelection:
                actions = [
                    ActionDef("Export Lines as Patch...", self.exportSelection),
                ]
            else:
                actions = [
                    ActionDef("Export Hunk as Patch...", lambda: self.exportHunk(clickedHunkID)),
                ]

        elif self.currentStagingState == StagingState.UNSTAGED:
            if hasSelection:
                actions = [
                    ActionDef("Stage Lines", self.stageSelection),
                    ActionDef("Discard Lines", self.discardSelection, QStyle.StandardPixmap.SP_TrashIcon),
                    ActionDef("Export Lines as Patch...", self.exportSelection),
                ]
            else:
                actions = [
                    ActionDef(F"Stage Hunk {clickedHunkID}", lambda: self.stageHunk(clickedHunkID)),
                    ActionDef(F"Discard Hunk {clickedHunkID}", lambda: self.discardHunk(clickedHunkID)),
                    ActionDef("Export Hunk as Patch...", lambda: self.exportHunk(clickedHunkID)),
                ]

        elif self.currentStagingState == StagingState.STAGED:
            if hasSelection:
                actions = [
                    ActionDef("Unstage Lines", self.unstageSelection),
                    ActionDef("Export Lines as Patch...", self.exportSelection),
                ]
            else:
                actions = [
                    ActionDef(F"Unstage Hunk {clickedHunkID}", lambda: self.unstageHunk(clickedHunkID)),
                    ActionDef("Export Hunk as Patch...", lambda: self.exportHunk(clickedHunkID)),
                ]

        else:
            QMessageBox.warning(self, "DiffView", F"Unknown staging state: {self.currentStagingState}")
            return

        actions += [
            None,
            ActionDef(F"&Word wrap", self.toggleWordWrap, checkState=1 if settings.prefs.diff_wordWrap else -1),
        ]

        menu = quickMenu(self, actions, menu)
        menu.exec_(event.globalPos())

    def toggleWordWrap(self):
        settings.prefs.diff_wordWrap = not settings.prefs.diff_wordWrap
        settings.prefs.write()
        self.refreshWordWrap()

    def keyPressEvent(self, event: QKeyEvent):
        k = event.key()
        if k in settings.KEYS_ACCEPT:
            if self.currentStagingState == StagingState.UNSTAGED:
                self.stageSelection()
            else:
                QApplication.beep()
        elif k in settings.KEYS_REJECT:
            if self.currentStagingState == StagingState.STAGED:
                self.unstageSelection()
            elif self.currentStagingState == StagingState.UNSTAGED:
                self.discardSelection()
            else:
                QApplication.beep()
        else:
            super().keyPressEvent(event)

    # ---------------------------------------------
    # Patch

    def findLineDataIndexAt(self, cursorPosition: int, firstLineDataIndex: int = 0):
        if not self.lineData:
            return -1
        index = bisect_right(self.lineCursorStartCache, cursorPosition, firstLineDataIndex)
        return index - 1

    def findHunkIDAt(self, cursorPosition: int):
        clickLineDataIndex = self.findLineDataIndexAt(cursorPosition)
        try:
            return self.lineData[clickLineDataIndex].hunkPos.hunkID
        except IndexError:
            return -1

    def extractSelection(self, reverse=False) -> bytes:
        cursor: QTextCursor = self.textCursor()
        posStart = cursor.selectionStart()
        posEnd = cursor.selectionEnd()

        # If line 1 is completely selected and the cursor has landed at the very beginning of line 2,
        # don't select line 2.
        if posEnd - posStart > 0:
            posEnd -= 1

        # Find indices of first and last LineData objects given the current selection
        biStart = self.findLineDataIndexAt(posStart)
        biEnd = self.findLineDataIndexAt(posEnd, biStart)

        return extractSubpatch(
            self.currentPatch,
            self.lineData[biStart].hunkPos,
            self.lineData[biEnd].hunkPos,
            reverse)

    def extractHunk(self, hunkID: int, reverse=False) -> bytes:
        # Find indices of first and last LineData objects given the current hunk
        hunkFirstLineIndex = bisect_left(self.lineHunkIDCache, hunkID, 0)
        hunkLastLineIndex = bisect_left(self.lineHunkIDCache, hunkID+1, hunkFirstLineIndex) - 1

        return extractSubpatch(
            self.currentPatch,
            self.lineData[hunkFirstLineIndex].hunkPos,
            self.lineData[hunkLastLineIndex].hunkPos,
            reverse)

    def applyEntirePatch(self, purpose: PatchPurpose):
        if purpose == PatchPurpose.UNSTAGE:
            porcelain.unstageFiles(self.repo, [self.currentPatch])
        elif purpose == PatchPurpose.STAGE:
            porcelain.stageFiles(self.repo, [self.currentPatch])
        elif purpose == PatchPurpose.DISCARD:
            porcelain.discardFiles(self.repo, [self.currentPatch.delta.new_file.path])
        else:
            raise KeyError(f"applyEntirePatch: unsupported purpose {purpose}")

    def onWantToApplyPartialPatch(self, purpose: PatchPurpose):
        verb: str = purpose.name

        qmb = QMessageBox(
            QMessageBox.Icon.Information,
            "Selection empty for partial patch",
            f"You haven’t selected any red/green lines to {verb.lower()}.",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Apply,
            parent=self)

        applyButton = qmb.button(QMessageBox.StandardButton.Apply)
        applyButton.setText(f"{verb.title()} entire file")
        applyButton.clicked.connect(lambda: self.applyEntirePatch(purpose))

        qmb.setWindowModality(Qt.WindowModality.WindowModal)
        qmb.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)  # don't leak dialog
        qmb.show()

    def applyPartialPatch(self, patchData: bytes, purpose: PatchPurpose):
        if not patchData:
            self.onWantToApplyPartialPatch(purpose)
            return

        discard = purpose == PatchPurpose.DISCARD
        if discard:
            Trash(self.repo).backupPatch(patchData, self.currentPatch.delta.new_file.path)
            applyLocation = pygit2.GIT_APPLY_LOCATION_WORKDIR
        else:
            applyLocation = pygit2.GIT_APPLY_LOCATION_INDEX

        try:
            diff = porcelain.applyPatch(self.repo, patchData, applyLocation)
        except GitError as e:
            excMessageBox(e, F"{purpose.name}: Apply Patch",
                          F"Failed to apply patch for operation “{purpose.name}”.", parent=self)
            return

        self.patchApplied.emit(NavPos())

    def exportPatch(self, patchData: bytes, saveInto=""):
        if not patchData:
            QApplication.beep()
            return

        name = os.path.basename(self.currentPatch.delta.new_file.path) + "[partial].patch"

        if saveInto:
            savePath = os.path.join(saveInto, name)
        else:
            savePath, _ = PersistentFileDialog.getSaveFileName(self, "Export selected lines", name)

        if savePath:
            with open(savePath, "wb") as file:
                file.write(patchData)

    def revertPatch(self, patchData: bytes):
        if not patchData:
            QApplication.beep()
            return

        diff = porcelain.patchApplies(self.repo, patchData, location=pygit2.GIT_APPLY_LOCATION_WORKDIR)
        if not diff:
            QMessageBox.warning(self, "Revert patch", "Couldn't revert this patch.\nThe code may have diverged too much from this revision.")
        else:
            diff = porcelain.applyPatch(self.repo, diff, location=pygit2.GIT_APPLY_LOCATION_WORKDIR)
            changedFile = get1FileChangedByDiff(diff)
            self.patchApplied.emit(NavPos("UNSTAGED", changedFile))  # send a NavPos to have RepoWidget show the file in the unstaged list

    def applySelection(self, purpose: PatchPurpose):
        reverse = purpose != PatchPurpose.STAGE
        patchData = self.extractSelection(reverse)
        self.applyPartialPatch(patchData, purpose)

    def applyHunk(self, hunkID: int, purpose: PatchPurpose):
        reverse = purpose != PatchPurpose.STAGE
        patchData = self.extractHunk(hunkID, reverse)
        self.applyPartialPatch(patchData, purpose)

    def stageSelection(self):
        self.applySelection(PatchPurpose.STAGE)

    def unstageSelection(self):
        self.applySelection(PatchPurpose.UNSTAGE)

    def discardSelection(self):
        qmb = QMessageBox(
            QMessageBox.Icon.Warning,
            "Really discard lines?",
            "Really discard the selected lines?\nThis cannot be undone!",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            parent=self)

        discardButton = qmb.button(QMessageBox.StandardButton.Discard)
        discardButton.setText("Discard lines")
        discardButton.clicked.connect(lambda: self.applySelection(PatchPurpose.DISCARD))

        qmb.setWindowModality(Qt.WindowModality.WindowModal)
        qmb.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)  # don't leak dialog
        qmb.show()

    def exportSelection(self, saveInto=""):
        patchData = self.extractSelection()
        self.exportPatch(patchData, saveInto)

    def revertSelection(self):
        patchData = self.extractSelection(reverse=True)
        self.revertPatch(patchData)

    def stageHunk(self, hunkID: int):
        self.applyHunk(hunkID, PatchPurpose.STAGE)

    def unstageHunk(self, hunkID: int):
        self.applyHunk(hunkID, PatchPurpose.UNSTAGE)

    def discardHunk(self, hunkID: int):
        qmb = QMessageBox(
            QMessageBox.Icon.Warning,
            "Really discard hunk?",
            "Really discard this hunk?\nThis cannot be undone!",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            parent=self)

        discardButton = qmb.button(QMessageBox.StandardButton.Discard)
        discardButton.setText("Discard hunk")
        discardButton.clicked.connect(lambda: self.applyHunk(hunkID, PatchPurpose.DISCARD))

        qmb.setWindowModality(Qt.WindowModality.WindowModal)
        qmb.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)  # don't leak dialog
        qmb.show()

    def exportHunk(self, hunkID: int, saveInto=""):
        patchData = self.extractHunk(hunkID)
        self.exportPatch(patchData, saveInto)

    def revertHunk(self, hunkID: int):
        patchData = self.extractHunk(hunkID, reverse=True)
        self.revertPatch(patchData)

    # ---------------------------------------------
    # Gutter (inspired by https://doc.qt.io/qt-5/qtwidgets-widgets-codeeditor-example.html)

    def gutterWidth(self) -> int:
        paddingString = '0' * (2*self.gutterMaxDigits + 2)
        return self.fontMetrics().horizontalAdvance(paddingString)

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)

        cr: QRect = self.contentsRect()
        self.gutter.setGeometry(QRect(cr.left(), cr.top(), self.gutterWidth(), cr.height()))

    def updateGutterWidth(self, newBlockCount: int):
        self.setViewportMargins(self.gutterWidth(), 0, 0, 0)

    def gutterPaintEvent(self, event: QPaintEvent):
        palette: QPalette = self.palette()

        painter = QPainter(self.gutter)
        painter.setFont(self.font())

        FH = self.fontMetrics().height()
        er = event.rect()
        gr = self.gutter.rect()

        # Background
        painter.fillRect(er, palette.color(QPalette.ColorRole.AlternateBase))

        # Draw separator
        gutterSepColor = palette.color(QPalette.ColorRole.PlaceholderText)
        gutterSepColor.setAlpha(80)
        painter.fillRect(gr.x() + gr.width() - 1, er.y(), 1, er.height(), gutterSepColor)

        block: QTextBlock = self.firstVisibleBlock()
        blockNumber = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())

        painter.setPen(palette.color(QPalette.ColorRole.PlaceholderText))
        while block.isValid() and top <= er.bottom():
            if blockNumber >= len(self.lineData):
                break

            ld = self.lineData[blockNumber]
            if block.isVisible() and bottom >= er.top():
                if ld.diffLine:
                    # Draw line numbers
                    old = str(ld.diffLine.old_lineno) if ld.diffLine.old_lineno > 0 else "·"
                    new = str(ld.diffLine.new_lineno) if ld.diffLine.new_lineno > 0 else "·"

                    colW = (gr.width() - 4) // 2
                    painter.drawText(0, top, colW, FH, Qt.AlignmentFlag.AlignRight, old)
                    painter.drawText(colW, top, colW, FH, Qt.AlignmentFlag.AlignRight, new)
                else:
                    # Draw hunk separator horizontal line
                    painter.fillRect(0, round((top+bottom)/2), gr.width(), 1, gutterSepColor)

            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            blockNumber += 1

        painter.end()

    def updateGutter(self, rect: QRect, dy: int):
        if dy != 0:
            self.gutter.scroll(0, dy)
        else:
            self.gutter.update(0, rect.y(), self.gutter.width(), rect.height())

        if rect.contains(self.viewport().rect()):
            self.updateGutterWidth(0)

    def getAnchorHomeLinePosition(self):
        cursor: QTextCursor = self.textCursor()

        # Snap anchor to start of home line
        cursor.setPosition(cursor.anchor(), QTextCursor.MoveMode.MoveAnchor)
        cursor.movePosition(QTextCursor.MoveOperation.StartOfLine, QTextCursor.MoveMode.MoveAnchor)

        return cursor.anchor()

    def getStartOfLineAt(self, point: QPoint):
        clickedCursor: QTextCursor = self.cursorForPosition(point)
        clickedCursor.movePosition(QTextCursor.MoveOperation.StartOfLine)
        return clickedCursor.position()

    def replaceCursor(self, cursor: QTextCursor):
        # Back up horizontal slider position
        hsb: QScrollBar = self.horizontalScrollBar()
        if hsb:
            hsbPos = hsb.sliderPosition()

        # Replace the cursor
        self.setTextCursor(cursor)

        # Restore horizontal slider position
        if hsb:
            hsb.setSliderPosition(hsbPos)

    def selectWholeLineAt(self, point: QPoint):
        clickedPosition = self.getStartOfLineAt(point)

        cursor: QTextCursor = self.textCursor()
        cursor.setPosition(clickedPosition)
        cursor.movePosition(QTextCursor.MoveOperation.EndOfLine, QTextCursor.MoveMode.KeepAnchor)

        self.replaceCursor(cursor)

    def selectWholeLinesTo(self, point: QPoint):
        homeLinePosition = self.getAnchorHomeLinePosition()
        clickedPosition = self.getStartOfLineAt(point)

        cursor: QTextCursor = self.textCursor()

        if homeLinePosition <= clickedPosition:
            # Move anchor to START of home line
            cursor.setPosition(homeLinePosition, QTextCursor.MoveMode.MoveAnchor)
            # Move cursor to END of clicked line
            cursor.setPosition(clickedPosition, QTextCursor.MoveMode.KeepAnchor)
            cursor.movePosition(QTextCursor.MoveOperation.EndOfLine, QTextCursor.MoveMode.KeepAnchor)
        else:
            # Move anchor to END of home line
            cursor.setPosition(homeLinePosition, QTextCursor.MoveMode.MoveAnchor)
            cursor.movePosition(QTextCursor.MoveOperation.EndOfLine, QTextCursor.MoveMode.MoveAnchor)
            # Move cursor to START of clicked line
            cursor.setPosition(clickedPosition, QTextCursor.MoveMode.KeepAnchor)
            cursor.movePosition(QTextCursor.MoveOperation.StartOfLine, QTextCursor.MoveMode.KeepAnchor)

        self.replaceCursor(cursor)
