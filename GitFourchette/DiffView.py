from PySide2.QtWidgets import *
from PySide2.QtGui import *
from PySide2.QtCore import *
import difflib
import re
import git
from typing import List

import settings

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


hunkRE = re.compile(r"^@@ -(\d+),(\d+) \+(\d+),(\d+) @@$")


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


class LineData:
    cursorStart : int
    lineA : int
    lineB : int
    data : str


class DiffView(QTextEdit):
    lineData: List[LineData]
    currentChange : git.diff.Diffable

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLineWrapMode(QTextEdit.NoWrap)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.doc = QTextDocument(self)
        self.setDocument(self.doc)
        self.setReadOnly(True)

    def setUntrackedContents(self, repo: git.Repo, path: str):
        self.doc.clear()
        self.setTabStopDistance(settings.monoFontMetrics.horizontalAdvance(' ' * settings.TAB_SPACES))
        cursor = QTextCursor(self.doc)
        cursor.setBlockFormat(plusBF)
        cursor.setBlockCharFormat(plusCF)
        cursor.insertText(open(repo.working_tree_dir + '/' + path, 'rb').read().decode('utf-8'))

    def setDiffContents(self, repo, change : git.diff.Diffable):
        self.currentChange = change
        if change.change_type == 'D':
            self.setFailureContents("File was deleted.")
            return

        self.doc.clear()
        self.setTabStopDistance(settings.monoFontMetrics.horizontalAdvance(' ' * settings.TAB_SPACES))
        cursor: QTextCursor = QTextCursor(self.doc)
        firstBlock = True

        # added files (that didn't exist before) don't have an a_blob
        if change.a_blob:
            a = change.a_blob.data_stream.read()
        else:
            a = b""

        if change.b_blob:
            b = change.b_blob.data_stream.read()
        else:
            b = open(repo.working_tree_dir + '/' + change.b_path, 'rb').read()

        a = a.decode('utf-8').splitlines(keepends=True)
        b = b.decode('utf-8').splitlines(keepends=True)

        self.lineData = []

        lineA = -1
        lineB = -1

        for line in difflib.unified_diff(a, b):
            # skip bogus diff header
            if line == "+++ \n" or line == "--- \n":
                continue

            ld = LineData()
            ld.cursorStart = cursor.position()
            ld.lineA = lineA
            ld.lineB = lineB
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
                trailer = "<CR>"
            elif line.endswith("\n"):
                trimBack = -1

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

    def setFailureContents(self, message):
        self.clear()
        self.setFont(QFontDatabase.systemFont(QFontDatabase.GeneralFont))
        self.setFontWeight(QFont.Weight.Bold)
        self.setTextColor(QColor(200, 0, 0))
        self.insertPlainText(message)

    def contextMenuEvent(self, event: QContextMenuEvent):
        menu: QMenu = self.createStandardContextMenu()
        before = menu.actions()[0]
        action1 = QAction("Stage Lines", self)
        action1.triggered.connect(self.stageLines)
        action2 = QAction("Discard Lines", self)
        action2.triggered.connect(self.discardLines)
        menu.insertAction(before, action1)
        menu.insertAction(before, action2)
        menu.insertSeparator(before)
        menu.exec_(event.globalPos())

    def stageLines(self):
        cursor = self.textCursor()
        posStart = cursor.selectionStart()
        posEnd = cursor.selectionEnd()

        if posEnd - posStart > 0:
            posEnd -= 1

        biStart = bisect(self.lineData, posStart, key=lambda ld: ld.cursorStart)
        biEnd = bisect(self.lineData, posEnd, biStart, key=lambda ld: ld.cursorStart)
        
        print(F"stage lines:  cursor({posStart}-{posEnd})  bisect({biStart}-{biEnd})")

        patch = ""
        patch += F"--- a/{self.currentChange.a_path}\n"
        patch += F"+++ b/{self.currentChange.b_path}\n"

        for ld in self.lineData[biStart-1 : biEnd]:
            if ld.data[0] in '@ ':
                continue
            hunkLenA = 0 if ld.data[0] == '+' else 1
            hunkLenB = 0 if ld.data[0] == '-' else 1
            patch += F"@@ -{ld.lineA},{hunkLenA} +{ld.lineB},{hunkLenB} @@\n"
            patch += ld.data
            #print(F"{ld.cursorStart}-{ld.cursorEnd} {ld.lineA} {ld.lineB} {ld.data.strip()}")

        print(patch)

    def discardLines(self):
        pass
