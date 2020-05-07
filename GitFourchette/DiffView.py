from PySide2.QtWidgets import *
from PySide2.QtGui import *
from PySide2.QtCore import *
import difflib

import globals

normalBF = QTextBlockFormat()
normalCF = QTextCharFormat()
normalCF.setFont(globals.monoFont)

plusBF = QTextBlockFormat()
plusBF.setBackground(QColor(220, 254, 225))

minusBF = QTextBlockFormat()
minusBF.setBackground(QColor(255, 227, 228))

arobaseBF = QTextBlockFormat()
arobaseCF = QTextCharFormat()
arobaseCF.setFont(globals.alternateFont)
arobaseCF.setForeground(QColor(0, 80, 240))

warningFormat = QTextCharFormat()
warningFormat.setForeground(QColor(255, 0, 0))
warningFormat.setFont(globals.alternateFont)


class DiffView(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLineWrapMode(QTextEdit.NoWrap)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.doc = QTextDocument(self)
        self.setDocument(self.doc)

    def setDiffContents(self, repo, change):
        if change.change_type == 'D':
            self.setFailureContents("File was deleted.")
            return

        self.doc.clear()
        self.setTabStopDistance(globals.monoFontMetrics.horizontalAdvance(' ' * globals.TAB_SPACES))
        cursor: QTextCursor = QTextCursor(self.doc)
        firstBlock = True

        a = change.a_blob.data_stream.read()

        if change.b_blob:
            b = change.b_blob.data_stream.read()
        else:
            b = open(repo.working_tree_dir + '/' + change.b_path, 'rb').read()

        a = a.decode('utf-8').splitlines(keepends=True)
        b = b.decode('utf-8').splitlines(keepends=True)

        for line in difflib.unified_diff(a, b):
            # skip bogus diff header
            if line == "+++ \n" or line == "--- \n":
                continue

            bf, cf = normalBF, normalCF
            trimFront, trimBack = 1, None
            trailer = None

            if line.startswith('@@'):
                bf, cf = arobaseBF, arobaseCF
                trimFront = 0
            elif line.startswith('+'):
                bf = plusBF
            elif line.startswith('-'):
                bf = minusBF
            else:
                pass # context line

            if line.endswith("\r\n"):
                trimBack = -2
                trailer = "<CR>"
            elif line.endswith("\n"):
                trimBack = -1

            if not firstBlock:
                cursor.insertBlock()
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
