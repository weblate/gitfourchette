from allqt import *
from bisect import bisect_left, bisect_right
from diffmodel import DiffModel
from patch import LineData, PatchPurpose, makePatchFromLines, applyPatch
from pygit2 import GitError, Patch, Repository
from stagingstate import StagingState
from util import excMessageBox, ActionDef, quickMenu
import settings
import trash


class DiffView(QTextEdit):
    patchApplied: Signal = Signal()

    lineData: list[LineData]
    lineCursorStartCache: list[int]
    lineHunkIDCache: list[int]
    currentStagingState: StagingState
    currentPatch: Patch
    currentGitRepo: Repository

    def __init__(self, parent=None):
        super().__init__(parent)
        #self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setReadOnly(True)
        self.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)

        # First-time init so callbacks don't crash looking for missing attributes
        self.lineData = []
        self.lineCursorStartCache = []
        self.lineHunkIDCache = []
        self.currentStagingState = None
        self.currentPatch = None
        self.currentGitRepo = None

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

        self.setDocument(dm.document)
        self.lineData = dm.lineData
        self.lineCursorStartCache = [ld.cursorStart for ld in self.lineData]
        self.lineHunkIDCache = [ld.hunkPos.hunkID for ld in self.lineData]

        tabWidth = settings.prefs.diff_tabSpaces

        # now reset defaults that are lost when changing documents
        self.setTabStopDistance(dm.style.monoFontMetrics.horizontalAdvance(' ' * tabWidth))
        self.refreshWordWrap(dm.forceWrap)
        self.setCursorWidth(2)

    def refreshWordWrap(self, forceWrap=False):
        if forceWrap or settings.prefs.diff_wordWrap:
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
            trash.trashRawPatch(self.currentGitRepo, patchData)

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
