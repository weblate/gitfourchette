from PySide2.QtWidgets import *
from PySide2.QtGui import *
from PySide2.QtCore import *
import re
import git
from typing import List
import os

import patch
import DiffActionSets
import settings
from status import gstatus
import trash
from util import excMessageBox

normalBF = QTextBlockFormat()
normalCF = QTextCharFormat()
normalCF.setFont(settings.monoFont)

plusBF = QTextBlockFormat()
plusBF.setBackground(QColor(220, 254, 225))
plusCF = normalCF

minusBF = QTextBlockFormat()
minusBF.setBackground(QColor(255, 227, 228))
minusCF = normalCF

arobaseBF = QTextBlockFormat()
arobaseCF = QTextCharFormat()
arobaseCF.setFont(settings.alternateFont)
arobaseCF.setForeground(QColor(0, 80, 240))

warningFormat = QTextCharFormat()
warningFormat.setForeground(QColor(255, 0, 0))
warningFormat.setFont(settings.alternateFont)


# Examples of matches:
# @@ -4,6 +4,7 @@
# @@ -1 +1,165 @@
# @@ -0,0 +1 @@
hunkRE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@$")


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

    def _replaceDocument(self, document: QTextDocument, forceWrap: bool = False):
        oldDocument = self.document()
        if oldDocument:
            oldDocument.deleteLater()  # avoid leaking memory/objects, even though we do set QTextDocument's parent to this QTextEdit
        self.setDocument(document)

        # now reset defaults that are lost when changing documents
        self.setTabStopDistance(settings.monoFontMetrics.horizontalAdvance(' ' * settings.prefs.diff_tabSpaces))
        if forceWrap:
            self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        else:
            self.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)

    def setUntrackedContents(self, repo: git.Repo, path: str):
        fullPath = os.path.join(repo.working_tree_dir, path)

        fileSize = os.path.getsize(fullPath)
        if fileSize > settings.prefs.diff_largeFileThreshold:
            self.setFailureContents(F"Large file warning: {fileSize:,} bytes")
            return

        try:
            with open(fullPath, 'rb') as f:
                contents: str = f.read().decode('utf-8')
        except UnicodeDecodeError as e:
            self.setFailureContents(F"File appears to be binary.\n{e}")
            return

        self.currentActionSet = DiffActionSets.untracked
        document = QTextDocument(self)  # recreating a document is faster than clearing the existing one
        cursor = QTextCursor(document)
        cursor.setBlockFormat(plusBF)
        cursor.setBlockCharFormat(plusCF)
        cursor.insertText(contents)
        self._replaceDocument(document)

    def setDiffContents(self, repo: git.Repo, change: git.Diff, diffActionSet: str):
        self.currentActionSet = diffActionSet
        self.currentGitRepo = repo
        self.currentChange = change

        if change.change_type == 'D':
            self.setFailureContents("File was deleted.")
            return

        if change.b_blob and change.b_blob.size > settings.prefs.diff_largeFileThreshold:
            self.setFailureContents(F"Large file warning: {change.b_blob.size:,} bytes")
            return
        if change.a_blob and change.a_blob.size > settings.prefs.diff_largeFileThreshold:
            self.setFailureContents(F"Large file warning: {change.a_blob.size:,} bytes")
            return

        try:
            patchLines: List[str] = patch.makePatchFromGitDiff(repo, change)
        except UnicodeDecodeError as e:
            self.setFailureContents(F"File appears to be binary.\n{e}")
            return

        document = QTextDocument(self)  # recreating a document is faster than clearing the existing one
        cursor: QTextCursor = QTextCursor(document)

        firstBlock = True
        self.lineData = []
        lineA = -1
        lineB = -1

        for line in patchLines:
            # skip diff header
            if line.startswith("+++ ") or line.startswith("--- "):
                continue

            ld = patch.LineData()
            ld.cursorStart = cursor.position()
            ld.lineA = lineA
            ld.lineB = lineB
            ld.diffLineIndex = len(self.lineData)
            ld.data = line
            self.lineData.append(ld)

            bf, cf = normalBF, normalCF
            trimFront, trimBack = 1, None
            trailer = None

            if line.startswith('@@'):
                bf, cf = arobaseBF, arobaseCF
                trimFront = 0
                hunkMatch = hunkRE.match(line)
                lineA = int(hunkMatch.group(1))
                lineB = int(hunkMatch.group(3))
            elif line.startswith('+'):
                bf = plusBF
                lineB += 1
            elif line.startswith('-'):
                bf = minusBF
                lineA += 1
            else:
                # context line
                lineA += 1
                lineB += 1

            if line.endswith("\r\n"):
                trimBack = -2
                if settings.prefs.diff_showStrayCRs:
                    trailer = "<CR>"
            elif line.endswith("\n"):
                trimBack = -1
            else:
                trailer = "<no newline at end of file>"

            if not firstBlock:
                cursor.insertBlock()
                ld.cursorStart = cursor.position()
            firstBlock = False

            cursor.setBlockFormat(bf)
            cursor.setCharFormat(cf)
            cursor.insertText(line[trimFront:trimBack])

            if trailer:
                cursor.setCharFormat(warningFormat)
                cursor.insertText(trailer)
                cursor.setCharFormat(cf)

        self._replaceDocument(document)

    def setFailureContents(self, message):
        document = QTextDocument(self)
        cursor = QTextCursor(document)
        cursor.setCharFormat(warningFormat)
        cursor.insertText(message)
        self._replaceDocument(document, forceWrap=True)

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