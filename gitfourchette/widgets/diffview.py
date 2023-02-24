from gitfourchette import log
from gitfourchette import porcelain
from gitfourchette import settings
from gitfourchette.actiondef import ActionDef
from gitfourchette.globalshortcuts import GlobalShortcuts
from gitfourchette.navhistory import NavPos
from gitfourchette.qt import *
from gitfourchette.stagingstate import StagingState
from gitfourchette.subpatch import extractSubpatch
from gitfourchette.trash import Trash
from gitfourchette.util import (PersistentFileDialog, excMessageBox, QSignalBlockerContext,
                                showWarning, askConfirmation, asyncMessageBox, stockIcon)
from gitfourchette.widgets.diffmodel import DiffModel, LineData
from bisect import bisect_left, bisect_right
from pygit2 import GitError, Patch, Repository, Diff
import enum
import os
import pygit2
import re


def get1FileChangedByDiff(diff: Diff):
    for p in diff:
        if p.delta.status != pygit2.GIT_DELTA_DELETED:
            return p.delta.new_file.path
    return ""


@enum.unique
class PatchPurpose(enum.IntFlag):
    STAGE = enum.auto()
    UNSTAGE = enum.auto()
    DISCARD = enum.auto()

    LINES = enum.auto()
    HUNK = enum.auto()
    FILE = enum.auto()

    VERB_MASK = STAGE | UNSTAGE | DISCARD

    @staticmethod
    def getName(purpose: 'PatchPurpose', verbOnly=False) -> str:
        pp = PatchPurpose
        if verbOnly:
            purpose &= pp.VERB_MASK
        dd = {
            pp.STAGE: translate("PatchPurpose", "Stage"),
            pp.UNSTAGE: translate("PatchPurpose", "Unstage"),
            pp.DISCARD: translate("PatchPurpose", "Discard"),
            pp.LINES | pp.STAGE: translate("PatchPurpose", "Stage lines"),
            pp.LINES | pp.UNSTAGE: translate("PatchPurpose", "Unstage lines"),
            pp.LINES | pp.DISCARD: translate("PatchPurpose", "Discard lines"),
            pp.HUNK | pp.STAGE: translate("PatchPurpose", "Stage hunk"),
            pp.HUNK | pp.UNSTAGE: translate("PatchPurpose", "Unstage hunk"),
            pp.HUNK | pp.DISCARD: translate("PatchPurpose", "Discard hunk"),
            pp.FILE | pp.STAGE: translate("PatchPurpose", "Stage file"),
            pp.FILE | pp.UNSTAGE: translate("PatchPurpose", "Unstage file"),
            pp.FILE | pp.DISCARD: translate("PatchPurpose", "Discard file"),
        }
        return dd.get(purpose, "???")


class DiffGutter(QWidget):
    diffView: 'DiffView'

    def __init__(self, parent):
        super().__init__(parent)
        self.diffView = parent

        if MACOS or WINDOWS:
            dpr = 4
        else:
            dpr = 1  # On Linux, Qt doesn't seem to support cursors at non-1 DPR
        pix = QPixmap(f"assets:right_ptr@{dpr}x")
        pix.setDevicePixelRatio(dpr)
        flippedCursor = QCursor(pix, hotX=19, hotY=5)
        self.setCursor(flippedCursor)

        # Enable customContextMenuRequested signal
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

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
    applyPatch = Signal(pygit2.Patch, bytes, PatchPurpose)
    revertPatch = Signal(pygit2.Patch, bytes)

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
        self.currentStagingState = StagingState.UNKNOWN
        self.currentPatch = None
        self.repo = None

        self.gutterMaxDigits = 0

        self.gutter = DiffGutter(self)
        self.updateRequest.connect(self.updateGutter)
        self.blockCountChanged.connect(self.updateGutterWidth)
        self.gutter.customContextMenuRequested.connect(lambda p: self.doContextMenu(self.gutter.mapToGlobal(p)))
        # self.cursorPositionChanged.connect(self.highlightCurrentLine)
        self.updateGutterWidth(0)

        # Work around control characters inserted by Qt 6 when copying text
        self.copyAvailable.connect(self.onCopyAvailable)

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
        self.doContextMenu(event.globalPos())

    def doContextMenu(self, globalPos: QPoint):
        # Get position of click in document
        clickedPosition = self.cursorForPosition(self.mapFromGlobal(globalPos)).position()

        cursor: QTextCursor = self.textCursor()
        hasSelection = cursor.hasSelection()

        # Find hunk at click position
        clickedHunkID = self.findHunkIDAt(clickedPosition)
        shortHunkHeader = ""
        if clickedHunkID >= 0:
            hunk: pygit2.DiffHunk = self.currentPatch.hunks[clickedHunkID]
            shortHunkHeader = re.sub(r"@@ (.+) @@.*", r"(\1)", hunk.header)

        actions = []

        if self.currentStagingState == StagingState.UNKNOWN:
            actions = []

        elif self.currentStagingState == StagingState.COMMITTED:
            if hasSelection:
                actions = [
                    ActionDef(self.tr("Export Lines as Patch..."), self.exportSelection),
                    ActionDef(self.tr("Revert Lines..."), self.revertSelection),
                ]
            else:
                actions = [
                    ActionDef(self.tr("Export Hunk {0} as Patch...").format(shortHunkHeader), lambda: self.exportHunk(clickedHunkID)),
                    ActionDef(self.tr("Revert Hunk..."), lambda: self.revertHunk(clickedHunkID)),
                ]

        elif self.currentStagingState == StagingState.UNTRACKED:
            if hasSelection:
                actions = [
                    ActionDef(self.tr("Export Lines as Patch..."), self.exportSelection),
                ]
            else:
                actions = [
                    ActionDef(self.tr("Export Hunk as Patch..."), lambda: self.exportHunk(clickedHunkID)),
                ]

        elif self.currentStagingState == StagingState.UNSTAGED:
            if hasSelection:
                actions = [
                    ActionDef(
                        self.tr("Stage Lines"),
                        self.stageSelection,
                        shortcuts=GlobalShortcuts.stageHotkeys,
                    ),
                    ActionDef(
                        self.tr("Discard Lines"),
                        self.discardSelection,
                        QStyle.StandardPixmap.SP_TrashIcon,
                        shortcuts=GlobalShortcuts.discardHotkeys,
                    ),
                    ActionDef(
                        self.tr("Export Lines as Patch..."),
                        self.exportSelection
                    ),
                ]
            else:
                actions = [
                    ActionDef(
                        self.tr("Stage Hunk {0}").format(shortHunkHeader),
                        lambda: self.stageHunk(clickedHunkID),
                    ),
                    ActionDef(
                        self.tr("Discard Hunk"),
                        lambda: self.discardHunk(clickedHunkID),
                    ),
                    ActionDef(self.tr("Export Hunk as Patch..."), lambda: self.exportHunk(clickedHunkID)),
                ]

        elif self.currentStagingState == StagingState.STAGED:
            if hasSelection:
                actions = [
                    ActionDef(
                        self.tr("Unstage Lines"),
                        self.unstageSelection,
                        shortcuts=GlobalShortcuts.discardHotkeys,
                    ),
                    ActionDef(
                        self.tr("Export Lines as Patch..."),
                        self.exportSelection,
                    ),
                ]
            else:
                actions = [
                    ActionDef(
                        self.tr("Unstage Hunk {0}").format(shortHunkHeader),
                        lambda: self.unstageHunk(clickedHunkID),
                    ),
                    ActionDef(
                        self.tr("Export Hunk as Patch..."),
                        lambda: self.exportHunk(clickedHunkID),
                    ),
                ]

        else:
            showWarning(self, "DiffView", F"Unknown staging state: {self.currentStagingState}")
            return

        actions += [
            None,
            ActionDef(self.tr("&Word wrap"), self.toggleWordWrap, checkState=1 if settings.prefs.diff_wordWrap else -1),
        ]

        bottom: QMenu = self.createStandardContextMenu()
        menu = ActionDef.makeQMenu(self, actions, bottom)
        bottom.deleteLater()  # don't need this menu anymore
        menu.setObjectName("DiffViewContextMenu")
        menu.exec(globalPos)
        menu.deleteLater()

    def toggleWordWrap(self):
        settings.prefs.diff_wordWrap = not settings.prefs.diff_wordWrap
        settings.prefs.write()
        self.refreshWordWrap()

    def keyPressEvent(self, event: QKeyEvent):
        k = event.key()
        if k in GlobalShortcuts.stageHotkeys:
            if self.currentStagingState == StagingState.UNSTAGED:
                self.stageSelection()
            else:
                QApplication.beep()
        elif k in GlobalShortcuts.discardHotkeys:
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

    def exportPatch(self, patchData: bytes, saveInto=""):
        if not patchData:
            QApplication.beep()
            return

        name = os.path.basename(self.currentPatch.delta.new_file.path) + "[partial].patch"

        if saveInto:
            savePath = os.path.join(saveInto, name)
        else:
            savePath, _ = PersistentFileDialog.getSaveFileName(self, self.tr("Export selected lines"), name)

        if savePath:
            with open(savePath, "wb") as file:
                file.write(patchData)

    def fireRevert(self, patchData: bytes):
        self.revertPatch.emit(self.currentPatch, patchData)

    def fireApplyLines(self, purpose: PatchPurpose):
        purpose |= PatchPurpose.LINES
        reverse = not (purpose & PatchPurpose.STAGE)
        patchData = self.extractSelection(reverse)
        self.applyPatch.emit(self.currentPatch, patchData, purpose)

    def fireApplyHunk(self, hunkID: int, purpose: PatchPurpose):
        purpose |= PatchPurpose.HUNK
        reverse = not (purpose & PatchPurpose.STAGE)
        patchData = self.extractHunk(hunkID, reverse)
        self.applyPatch.emit(self.currentPatch, patchData, purpose)

    def stageSelection(self):
        self.fireApplyLines(PatchPurpose.STAGE)

    def unstageSelection(self):
        self.fireApplyLines(PatchPurpose.UNSTAGE)

    def discardSelection(self):
        self.fireApplyLines(PatchPurpose.DISCARD)

    def exportSelection(self, saveInto=""):
        patchData = self.extractSelection()
        self.exportPatch(patchData, saveInto)

    def revertSelection(self):
        patchData = self.extractSelection(reverse=True)
        self.fireRevert(patchData)

    def stageHunk(self, hunkID: int):
        self.fireApplyHunk(hunkID, PatchPurpose.STAGE)

    def unstageHunk(self, hunkID: int):
        self.fireApplyHunk(hunkID, PatchPurpose.UNSTAGE)

    def discardHunk(self, hunkID: int):
        self.fireApplyHunk(hunkID, PatchPurpose.DISCARD)

    def exportHunk(self, hunkID: int, saveInto=""):
        patchData = self.extractHunk(hunkID)
        self.exportPatch(patchData, saveInto)

    def revertHunk(self, hunkID: int):
        patchData = self.extractHunk(hunkID, reverse=True)
        self.fireRevert(patchData)

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

    def onCopyAvailable(self, yes: bool):
        if QSysInfo.productType() != "windows":
            if yes:
                QApplication.clipboard().changed.connect(self.fixU2029InClipboard)
            else:
                QApplication.clipboard().changed.disconnect(self.fixU2029InClipboard)

    def fixU2029InClipboard(self, mode: QClipboard.Mode):
        """
        Qt 6 replaces line breaks with U+2029 (PARAGRAPH SEPARATOR) when copying
        text from a QPlainTextEdit. Let's restore the line breaks.

        https://doc.qt.io/qt-6/qtextcursor.html#selectedText
        "If the selection obtained from an editor spans a line break, the text
        will contain a Unicode U+2029 paragraph separator character instead of
        a newline \n character. Use QString::replace() to replace these
        characters with newlines."
        """

        # The copied data probably didn't originate from the DiffView if it doesn't have focus
        if not self.hasFocus():
            return

        clipboard = QApplication.clipboard()

        # Even if we have focus, another process might have modified the clipboard in the background.
        # So, make sure our application owns the data in the clipboard.
        ownsData = ((mode == QClipboard.Mode.Clipboard and clipboard.ownsClipboard())
                    or (mode == QClipboard.Mode.Selection and clipboard.ownsSelection())
                    or (mode == QClipboard.Mode.FindBuffer and clipboard.ownsFindBuffer()))
        if not ownsData:
            return

        log.info("DiffView", F"Scrubbing U+2029 characters from clipboard ({mode})")
        text = clipboard.text(mode).replace("\u2029", "\n")
        with QSignalBlockerContext(clipboard):
            clipboard.setText(text, mode)
