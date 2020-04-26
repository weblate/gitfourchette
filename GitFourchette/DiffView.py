from PySide2.QtWidgets import *
from PySide2.QtGui import *
from PySide2.QtCore import *
import difflib

import globals

class DiffView(QTextEdit):
    def __init__(self, parent=None):
        super(__class__, self).__init__(parent)
        self.setTabStopDistance(globals.TAB_SPACES * self.fontMetrics().horizontalAdvance(' '))
        self.setLineWrapMode(QTextEdit.NoWrap)

    def setDiffContents(self, repo, change):
        if change.change_type == 'D':
            self.clear()
            self.setText("File was deleted.")
            return
        a = change.a_blob.data_stream.read()
        # print("A:", a)
        if change.b_blob:
            b = change.b_blob.data_stream.read()
        else:
            b = open(repo.working_tree_dir + '/' + change.b_path, 'rb').read()
        # print("B:", b)
        a = a.decode('utf-8').splitlines(keepends=True)
        b = b.decode('utf-8').splitlines(keepends=True)
        self.clear()
        self.setFont(globals.monoFont)
        for line in difflib.unified_diff(a, b):
            if line == "+++ \n" or line == "--- \n":
                continue
            if line.startswith('@@'):
                self.setTextBackgroundColor(QColor(255, 255, 255))
                self.setTextColor(QColor(0, 0, 200))
            elif line.startswith('+'):
                line = line[1:]
                self.setTextBackgroundColor(QColor(220, 254, 225))
            elif line.startswith('-'):
                line = line[1:]
                self.setTextBackgroundColor(QColor(255, 227, 228))
            else:
                line = line[1:]
                self.setTextBackgroundColor(QColor(255, 255, 255))
                self.setTextColor(QColor(80, 80, 80))
            self.insertPlainText(line)

    def setShittyContents(self, message):
        self.clear()
        self.setFont(QFontDatabase.systemFont(QFontDatabase.GeneralFont))
        self.setFontWeight(QFont.Weight.Bold)
        self.setTextColor(QColor(200, 0, 0))
        self.insertPlainText(message)
