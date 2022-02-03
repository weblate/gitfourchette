from allqt import *
from bisect import bisect_left, bisect_right
from patch import LineData, PatchPurpose, makePatchFromLines, applyPatch
from pygit2 import GitError, Patch, Repository
from stagingstate import StagingState
from trash import Trash
from util import excMessageBox, ActionDef, quickMenu
from widgets.diffmodel import DiffModel
import settings


class DiffGutter(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.diffView = parent

    def sizeHint(self) -> QSize:
        return QSize(self.diffView.gutterWidth(), 0)

    def paintEvent(self, event: QPaintEvent):
        self.diffView.gutterPaintEvent(event)


class DiffView(QPlainTextEdit):
    patchApplied: Signal = Signal()

    lineData: list[LineData]
    lineCursorStartCache: list[int]
    lineHunkIDCache: list[int]
    currentStagingState: StagingState
    currentPatch: Patch
    currentGitRepo: Repository

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setReadOnly(True)
        self.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)

        # First-time init so callbacks don't crash looking for missing attributes
        self.lineData = []
        self.lineCursorStartCache = []
        self.lineHunkIDCache = []
        self.currentStagingState = None
        self.currentPatch = None
        self.currentGitRepo = None

        self.gutterMaxDigits = 0

        self.gutter = DiffGutter(self)
        self.updateRequest.connect(self.updateGutter)
        self.blockCountChanged.connect(self.updateGutterWidth)
        # self.cursorPositionChanged.connect(self.highlightCurrentLine)
        self.updateGutterWidth(0)

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

    def replaceDocument(self, repo: Repository, patch: Patch, stagingState: StagingState, dm: DiffModel):
        oldDocument = self.document()
        if oldDocument:
            oldDocument.deleteLater()  # avoid leaking memory/objects, even though we do set QTextDocument's parent to this QTextEdit

        self.currentStagingState = stagingState
        self.currentGitRepo = repo
        self.currentPatch = patch

        self.setFont(dm.document.defaultFont())
        self.setDocument(dm.document)

        self.lineData = dm.lineData
        self.lineCursorStartCache = [ld.cursorStart for ld in self.lineData]
        self.lineHunkIDCache = [ld.hunkPos.hunkID for ld in self.lineData]

        tabWidth = settings.prefs.diff_tabSpaces

        # now reset defaults that are lost when changing documents
        self.setTabStopDistance(QFontMetrics(dm.document.defaultFont()).horizontalAdvance(' ' * tabWidth))
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
            self.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        else:
            self.setWordWrapMode(QTextOption.NoWrap)

    def contextMenuEvent(self, event: QContextMenuEvent):
        # Get position of click in document
        clickedPosition = self.cursorForPosition(event.pos()).position()

        # Find hunk at click position
        clickedHunkID = self.findHunkIDAt(clickedPosition)

        menu: QMenu = self.createStandardContextMenu()

        actions = []

        actionWordWrap = ActionDef(F"&Word wrap", self.toggleWordWrap, checkState=1 if settings.prefs.diff_wordWrap else -1)

        if self.currentStagingState in [None, StagingState.COMMITTED, StagingState.UNTRACKED]:
            actions = [
                actionWordWrap
            ]
        elif self.currentStagingState == StagingState.UNSTAGED:
            actions = [
                ActionDef("Stage Lines", self.stageLines),
                ActionDef("Discard Lines", self.discardLines, QStyle.SP_TrashIcon),
                None,
                ActionDef(F"Stage Hunk {clickedHunkID}", lambda: self.stageHunk(clickedHunkID)),
                ActionDef(F"Discard Hunk {clickedHunkID}", lambda: self.discardHunk(clickedHunkID)),
                None,
                actionWordWrap
            ]
        elif self.currentStagingState == StagingState.STAGED:
            actions = [
                ActionDef("Unstage Lines", self.unstageLines),
                ActionDef(F"Unstage Hunk {clickedHunkID}", lambda: self.unstageHunk(clickedHunkID)),
                None,
                actionWordWrap
            ]
        else:
            QMessageBox.warning(self, "DiffView", F"Unknown staging state: {self.currentStagingState}")

        if actions:
            menu = quickMenu(self, actions, menu)

        menu.exec_(event.globalPos())

    def toggleWordWrap(self):
        settings.prefs.diff_wordWrap = not settings.prefs.diff_wordWrap
        settings.prefs.write()
        self.refreshWordWrap()

    def _applyPatch(self, firstLineDataIndex: int, lastLineDataIndex: int, purpose: PatchPurpose):
        reverse = purpose != PatchPurpose.STAGE

        patchData = makePatchFromLines(
            self.currentPatch.delta.old_file.path,
            self.currentPatch.delta.new_file.path,
            self.currentPatch,
            self.lineData[firstLineDataIndex].hunkPos,
            self.lineData[lastLineDataIndex].hunkPos,
            reverse)

        if not patchData:
            QMessageBox.information(self, "Nothing to patch",
                                    "Select one or more red or green lines before applying a partial patch.")
            return

        if purpose == PatchPurpose.DISCARD:
            Trash(self.currentGitRepo).backupPatch(patchData, self.currentPatch.delta.new_file.path)

        try:
            applyPatch(self.currentGitRepo, patchData, purpose)
        except GitError as e:
            excMessageBox(e, F"{purpose.name}: Apply Patch",
                          F"Failed to apply patch for operation “{purpose.name}”.", parent=self)

        self.patchApplied.emit()

    def _applyPatchFromSelectedLines(self, purpose: PatchPurpose):
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

        print(F"{purpose.name} lines:  cursor({posStart}-{posEnd})  bisect({biStart}-{biEnd})")

        self._applyPatch(biStart, biEnd, purpose)

    def stageLines(self):
        self._applyPatchFromSelectedLines(PatchPurpose.STAGE)

    def unstageLines(self):
        self._applyPatchFromSelectedLines(PatchPurpose.UNSTAGE)

    def discardLines(self):
        rc = QMessageBox.warning(self, "Really discard lines?",
                                 "Really discard the selected lines?\nThis cannot be undone!",
                                 QMessageBox.Discard | QMessageBox.Cancel)
        if rc == QMessageBox.Discard:
            self._applyPatchFromSelectedLines(PatchPurpose.DISCARD)

    def _applyHunk(self, hunkID: int, purpose: PatchPurpose):
        # Find indices of first and last LineData objects given the current hunk
        hunkFirstLineIndex = bisect_left(self.lineHunkIDCache, hunkID, 0)
        hunkLastLineIndex = bisect_left(self.lineHunkIDCache, hunkID+1, hunkFirstLineIndex) - 1

        print(F"{purpose.name} hunk #{hunkID}:  line data indices {hunkFirstLineIndex}-{hunkLastLineIndex}")

        self._applyPatch(hunkFirstLineIndex, hunkLastLineIndex, purpose)

    def stageHunk(self, hunkID: int):
        self._applyHunk(hunkID, PatchPurpose.STAGE)

    def unstageHunk(self, hunkID: int):
        self._applyHunk(hunkID, PatchPurpose.UNSTAGE)

    def discardHunk(self, hunkID: int):
        rc = QMessageBox.warning(self, "Really discard hunk?",
                                 "Really discard this hunk?\nThis cannot be undone!",
                                 QMessageBox.Discard | QMessageBox.Cancel)
        if rc == QMessageBox.Discard:
            self._applyHunk(hunkID, PatchPurpose.DISCARD)

    def keyPressEvent(self, event: QKeyEvent):
        k = event.key()
        if k in settings.KEYS_ACCEPT:
            if self.currentStagingState == StagingState.UNSTAGED:
                self.stageLines()
            else:
                QApplication.beep()
        elif k in settings.KEYS_REJECT:
            if self.currentStagingState == StagingState.STAGED:
                self.unstageLines()
            elif self.currentStagingState == StagingState.UNSTAGED:
                self.discardLines()
            else:
                QApplication.beep()
        else:
            super().keyPressEvent(event)

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

        GW = self.gutter.width()
        FH = self.fontMetrics().height()
        er = event.rect()

        # Background
        painter.fillRect(er, palette.color(QPalette.ColorRole.Base))

        # Draw separator
        gutterSepColor = palette.color(QPalette.PlaceholderText)
        gutterSepColor.setAlpha(80)
        painter.fillRect(er.x() + er.width() - 1, er.y(), 1, er.height(), gutterSepColor)

        block: QTextBlock = self.firstVisibleBlock()
        blockNumber = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())

        painter.setPen(palette.color(QPalette.PlaceholderText))
        while block.isValid() and top <= er.bottom():
            if blockNumber >= len(self.lineData):
                break

            ld = self.lineData[blockNumber]
            if ld.diffLine and block.isVisible() and bottom >= er.top():
                old = str(ld.diffLine.old_lineno) if ld.diffLine.old_lineno > 0 else "·"
                new = str(ld.diffLine.new_lineno) if ld.diffLine.new_lineno > 0 else "·"

                colW = (GW-4)//2
                painter.drawText(0, top, colW, FH, Qt.AlignRight, old)
                painter.drawText(colW, top, colW, FH, Qt.AlignRight, new)

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
