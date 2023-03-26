from gitfourchette import log
from gitfourchette.qt import *
from gitfourchette import settings
from gitfourchette.widgets.diffmodel import DiffConflict
from gitfourchette.widgets.ui_conflictview import Ui_ConflictView
from gitfourchette.util import tweakWidgetFont
import pygit2


class ConflictView(QWidget):
    hardSolve = Signal(str, pygit2.Oid)
    markSolved = Signal(str)
    openFile = Signal(str)
    openMergeTool = Signal(DiffConflict)

    currentConflict: DiffConflict

    def __init__(self, parent):
        super().__init__(parent)
        self.ui = Ui_ConflictView()
        self.ui.setupUi(self)

        tweakWidgetFont(self.ui.titleLabel, 150, bold=True)

        self.currentConflict = None

        self.ui.mergeToolButton.setText(self.ui.mergeToolButton.text().format(settings.getMergeToolName()))

        self.ui.oursButton.clicked.connect(lambda: self.hardSolve.emit(self.currentConflict.ours.path, self.currentConflict.ours.id))
        self.ui.theirsButton.clicked.connect(lambda: self.hardSolve.emit(self.currentConflict.ours.path, self.currentConflict.theirs.id))
        self.ui.markSolvedButton.clicked.connect(lambda: self.markSolved.emit(self.currentConflict.ours.path))
        self.ui.editFileButton.clicked.connect(lambda: self.openFile.emit(self.currentConflict.ours.path))
        self.ui.mergeToolButton.clicked.connect(lambda: self.openMergeTool.emit(self.currentConflict))

    def clear(self):
        self.currentConflict = None

    def displayConflict(self, conflict: DiffConflict):
        self.currentConflict = conflict

    def refreshPrefs(self):
        self.ui.retranslateUi(self)
        self.ui.mergeToolButton.setText(self.ui.mergeToolButton.text().format(settings.getMergeToolName()))
