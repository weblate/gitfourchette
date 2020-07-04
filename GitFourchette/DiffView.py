from PySide2.QtWidgets import *
from PySide2.QtGui import *
from PySide2.QtCore import *
import re
import git
from typing import List

import patch
import DiffActionSets
import settings
from status import gstatus
import trash
from util import excMessageBox
import DiffModel


def bisect(a, x, lo=0, hi=None, key=lambda x: x):
    assert lo >= 0, "low must be non-negative"
    hi = hi or len(a)
    while lo < hi:
        mid = (lo+hi)//2
        if x < key(a[mid]):
            hi = mid
        else:
            lo = mid+1
    return lo


class DiffView(QTextEdit):
    patchApplied: Signal = Signal()

    lineData: List[patch.LineData]
    currentActionSet: str
    currentChange: git.Diff
    currentGitRepo: git.Repo

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLineWrapMode(QTextEdit.NoWrap)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setReadOnly(True)
        self.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)

    def replaceDocument(self, repo: git.Repo, diff: git.Diff, diffActionSet: str, dm: DiffModel):
        oldDocument = self.document()
        if oldDocument:
            oldDocument.deleteLater()  # avoid leaking memory/objects, even though we do set QTextDocument's parent to this QTextEdit

        self.currentActionSet = diffActionSet
        self.currentGitRepo = repo
        self.currentChange = diff

        self.setDocument(dm.document)
        self.lineData = dm.lineData

        # now reset defaults that are lost when changing documents
        self.setTabStopDistance(settings.monoFontMetrics.horizontalAdvance(' ' * settings.prefs.diff_tabSpaces))
        if dm.forceWrap:
            self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        else:
            self.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)

        self.setCursorWidth(2)

    def contextMenuEvent(self, event: QContextMenuEvent):
        menu: QMenu = self.createStandardContextMenu()
        before = menu.actions()[0]

        actions = []

        if self.currentActionSet is None:
            pass
        elif self.currentActionSet == DiffActionSets.untracked:
            pass
        elif self.currentActionSet == DiffActionSets.unstaged:
            action1 = QAction("Stage Lines", self)
            action1.triggered.connect(self.stageLines)
            action2 = QAction("Discard Lines", self)
            action2.triggered.connect(self.discardLines)
            actions = [action1, action2]
        elif self.currentActionSet == DiffActionSets.staged:
            action1 = QAction("Unstage Lines", self)
            action1.triggered.connect(self.unstageLines)
            actions = [action1]
        else:
            print(F"unknown diff action set: {self.currentActionSet}")

        if actions:
            for a in actions:
                menu.insertAction(before, a)
            menu.insertSeparator(before)

        menu.exec_(event.globalPos())

    def _applyLines(self, cached=True, reverse=False, trashBackup=False):
        cursor = self.textCursor()
        posStart = cursor.selectionStart()
        posEnd = cursor.selectionEnd()

        if posEnd - posStart > 0:
            posEnd -= 1

        biStart = bisect(self.lineData, posStart, key=lambda ld: ld.cursorStart)
        biEnd = bisect(self.lineData, posEnd, biStart, key=lambda ld: ld.cursorStart)

        print(F"{'un' if reverse else ''}stage lines:  cursor({posStart}-{posEnd})  bisect({biStart}-{biEnd})")

        biStart -= 1

        patchData = patch.makePatchFromLines(self.currentChange.a_path, self.currentChange.b_path, self.lineData, biStart, biEnd, cached=cached)

        if not patchData:
            gstatus.setText("Nothing to patch. Select one or more red or green lines before applying.")
            QApplication.beep()
            return

        if trashBackup:
            trash.trashRawPatch(self.currentGitRepo, patchData)

        try:
            patch.applyPatch(self.currentGitRepo, patchData, cached=cached, reverse=reverse)
        except git.GitCommandError as e:
            excMessageBox(e, "Apply Patch", "Failed to apply patch.", parent=self)

        self.patchApplied.emit()

    def stageLines(self):
        self._applyLines(reverse=False)

    def unstageLines(self):
        self._applyLines(reverse=True)

    def discardLines(self):
        self._applyLines(cached=False, reverse=True, trashBackup=True)

    def keyPressEvent(self, event: QKeyEvent):
        k = event.key()
        if k in settings.KEYS_ACCEPT:
            if self.currentActionSet == DiffActionSets.unstaged:
                self.stageLines()
            else:
                QApplication.beep()
        elif k in settings.KEYS_REJECT:
            if self.currentActionSet == DiffActionSets.staged:
                self.unstageLines()
            elif self.currentActionSet == DiffActionSets.unstaged:
                self.discardLines()
            else:
                QApplication.beep()
        else:
            super().keyPressEvent(event)