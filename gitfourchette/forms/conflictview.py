import pygit2

from gitfourchette import settings
from gitfourchette.diffview.specialdiff import DiffConflict
from gitfourchette.filelists.filelistmodel import STATUS_ICONS
from gitfourchette.forms.ui_conflictview import Ui_ConflictView
from gitfourchette.porcelain import BLANK_OID
from gitfourchette.qt import *
from gitfourchette.toolbox import *


class ConflictView(QWidget):
    hardSolve = Signal(str, pygit2.Oid)
    markSolved = Signal(str)
    openFile = Signal(str)
    openMergeTool = Signal(DiffConflict)

    currentConflict: DiffConflict | None

    def __init__(self, parent):
        super().__init__(parent)

        self.currentConflict = None

        self.ui = Ui_ConflictView()
        self.ui.setupUi(self)

        self.ui.deletedByUsAdd.setIcon(STATUS_ICONS['A'])
        self.ui.deletedByUsDelete.setIcon(STATUS_ICONS['D'])
        tweakWidgetFont(self.ui.titleLabel, 150, bold=True)

        self.ui.mergeToolButton.setText(self.ui.mergeToolButton.text().format(settings.getMergeToolName()))

        self.ui.oursButton.clicked.connect(lambda: self.hardSolve.emit(self.currentConflict.ours.path, self.currentConflict.ours.id))
        self.ui.theirsButton.clicked.connect(lambda: self.hardSolve.emit(self.currentConflict.ours.path, self.currentConflict.theirs.id))
        self.ui.markSolvedButton.clicked.connect(lambda: self.markSolved.emit(self.currentConflict.ours.path))
        self.ui.editFileButton.clicked.connect(lambda: self.openFile.emit(self.currentConflict.ours.path))
        self.ui.mergeToolButton.clicked.connect(lambda: self.openMergeTool.emit(self.currentConflict))

        self.ui.deletedByUsDelete.clicked.connect(lambda: self.hardSolve.emit(self.currentConflict.theirs.path, BLANK_OID))
        self.ui.deletedByUsAdd.clicked.connect(lambda: self.hardSolve.emit(self.currentConflict.theirs.path, self.currentConflict.theirs.id))

    def clear(self):
        self.currentConflict = None

    def displayConflict(self, conflict: DiffConflict):
        self.currentConflict = conflict

        self.ui.retranslateUi(self)

        if not conflict:
            pass
        elif conflict.deletedByUs:
            self.ui.reconcileStack.setCurrentWidget(self.ui.reconcileDeletedByUs)
            theirs = os.path.basename(conflict.theirs.path)
            formatWidgetText(self.ui.deletedByUsText, escape(theirs))
            formatWidgetText(self.ui.deletedByUsAdd, escamp(theirs))
        else:
            self.ui.reconcileStack.setCurrentWidget(self.ui.reconcile3Way)
            formatWidgetText(self.ui.mergeToolButton, settings.getMergeToolName())

    def refreshPrefs(self):
        self.displayConflict(self.currentConflict)

