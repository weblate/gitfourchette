from PySide2.QtWidgets import *
from PySide2.QtGui import *
from PySide2.QtCore import *
import difflib

import globals

contextFormat = QTextBlockFormat()

plusFormat = QTextBlockFormat()
plusFormat.setBackground(QColor(220, 254, 225))

minusFormat = QTextBlockFormat()
minusFormat.setBackground(QColor(255, 227, 228))

arobaseFormat = QTextBlockFormat()
arobaseFormat.setBackground(QColor(0, 0, 200))


class DiffView(QTextEdit):
    def __init__(self, parent=None):
        super(__class__, self).__init__(parent)
        self.setTabStopDistance(globals.TAB_SPACES * self.fontMetrics().horizontalAdvance(' '))
        self.setLineWrapMode(QTextEdit.NoWrap)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.doc = QTextDocument(self)
        self.setDocument(self.doc)
        self.setFont(globals.monoFont)

    def setDiffContents(self, repo, change):
        if change.change_type == 'D':
            self.setFailureContents("File was deleted.")
            return

        self.doc.clear()
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
            if line == "+++ \n" or line == "--- \n":
                continue

            fmt = contextFormat
            trimFront = 1
            trimBack = -1
            if line.startswith('@@'):
                fmt = arobaseFormat
                trimFront = 0
            elif line.startswith('+'):
                fmt = plusFormat
            elif line.startswith('-'):
                fmt = minusFormat

            if not firstBlock:
                cursor.insertBlock()
            firstBlock = False
            cursor.setBlockFormat(fmt)
            cursor.insertText(line[trimFront:trimBack])

    def setFailureContents(self, message):
        self.clear()
        self.setFont(QFontDatabase.systemFont(QFontDatabase.GeneralFont))
        self.setFontWeight(QFont.Weight.Bold)
        self.setTextColor(QColor(200, 0, 0))
        self.insertPlainText(message)
