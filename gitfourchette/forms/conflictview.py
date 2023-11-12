from gitfourchette import settings
from gitfourchette.diffview.specialdiff import DiffConflict
from gitfourchette.exttools import PREFKEY_MERGETOOL
from gitfourchette.forms.ui_conflictview import Ui_ConflictView
from gitfourchette.porcelain import NULL_OID
from gitfourchette.qt import *
from gitfourchette.tasks import HardSolveConflict
from gitfourchette.toolbox import *


class ConflictView(QWidget):
    openMergeTool = Signal(DiffConflict)
    openPrefs = Signal(str)
    linkActivated = Signal(str)

    currentConflict: DiffConflict | None

    def __init__(self, parent):
        super().__init__(parent)

        self.currentConflict = None

        self.ui = Ui_ConflictView()
        self.ui.setupUi(self)

        self.setBackgroundRole(QPalette.ColorRole.Base)
        self.setAutoFillBackground(True)

        def bindRadio(radio: QRadioButton):
            # Keep lambdas separate from for loop due to PYSIDE-2524 (buggy lambda capture if signal has default args)
            name = radio.objectName().removeprefix("radio").lower()
            assert name in self.helpTexts()
            radio.clicked.connect(lambda: self.setConfirmCaption(radio.text()))
            radio.clicked.connect(lambda: self.ui.explainer.setText(self.helpTexts()[name]))
        for radio in self.ui.groupBox.findChildren(QRadioButton):
            bindRadio(radio)

        tweakWidgetFont(self.ui.titleLabel, 130)
        tweakWidgetFont(self.ui.explainer, 90)

        self.ui.explainer.linkActivated.connect(self.linkActivated)
        self.ui.confirmButton.clicked.connect(self.onConfirm)

        self.reformatWidgetText()

    def onConfirm(self):
        conflict = self.currentConflict

        if not conflict:
            return

        elif conflict.deletedByUs:
            b = self.ui.radioGroupDbu.checkedButton()
            if not b:
                pass
            elif b is self.ui.radioDbuTheirs:
                self.hardSolve(conflict.theirs.path, conflict.theirs.id)
            elif b is self.ui.radioDbuOurs:  # ignore incoming change, keep deletion
                self.hardSolve(conflict.theirs.path, NULL_OID)

        elif conflict.deletedByThem:
            b = self.ui.radioGroupDbt.checkedButton()
            if not b:
                pass
            elif b is self.ui.radioDbtTheirs:  # accept deletion
                self.hardSolve(conflict.ours.path, NULL_OID)
            elif b is self.ui.radioDbtOurs:  # ignore incoming deletion
                self.hardSolve(conflict.ours.path, conflict.ours.id)

        else:
            b = self.ui.radioGroupBoth.checkedButton()
            if b is self.ui.radioOurs:
                self.hardSolve(conflict.ours.path, conflict.ours.id)
            elif b is self.ui.radioTheirs:
                self.hardSolve(conflict.ours.path, conflict.theirs.id)
            elif b is self.ui.radioTool:
                self.openMergeTool.emit(conflict)

    @staticmethod
    def hardSolve(path: str, oid=NULL_OID):
        HardSolveConflict.invoke(path, oid)

    def clear(self):
        self.currentConflict = None

    def displayConflict(self, conflict: DiffConflict):
        assert conflict is not None, "don't call displayConflict with None"

        self.currentConflict = conflict

        for radio in self.ui.groupBox.findChildren(QRadioButton):
            radio.setChecked(False)
            radio.setVisible(False)

        self.ui.retranslateUi(self)
        self.reformatWidgetText()

        if not conflict:
            pass

        elif conflict.deletedByUs:
            self.ui.subtitleLabel.setText(self.tr(
                "<b>Deleted by us:</b> this file was deleted from <i>our</i> branch, "
                "but <i>their</i> branch kept it and made changes to it."))
            for radio in self.ui.radioGroupDbu.buttons():
                radio.setVisible(True)

        elif conflict.deletedByThem:
            self.ui.subtitleLabel.setText(self.tr(
                "<b>Deleted by them:</b> we’ve made changes to this file, "
                "but <i>their</i> branch has deleted it."))
            for radio in self.ui.radioGroupDbt.buttons():
                radio.setVisible(True)

        else:
            self.ui.subtitleLabel.setText(self.tr(
                "<b>Modified by both:</b> This file has received changes from both <i>our</i> branch and <i>their</i> branch."))
            for radio in self.ui.radioGroupBoth.buttons():
                radio.setVisible(True)

    def reformatWidgetText(self):
        formatWidgetText(self.ui.radioTool, tool=settings.getMergeToolName())

        conflict = self.currentConflict
        if not conflict:
            return

        if conflict.ours:
            displayPath = conflict.ours.path
        else:
            displayPath = conflict.theirs.path

        formatWidgetText(self.ui.titleLabel, escape(os.path.basename(displayPath)))

    def setConfirmCaption(self, s: str):
        self.ui.confirmButton.setText(s)
        self.ui.confirmButton.setEnabled(True)

    def refreshPrefs(self):
        if self.currentConflict:
            self.displayConflict(self.currentConflict)

    def helpTexts(self):
        return {
            "tool":
                str.format(
                    self.tr("You will be able to merge the changes in {tool}. When you are done merging, "
                            "save the file in {tool} and come back to {app} to finish solving the conflict."
                            ) + " <a href='{settingsLink}'>{selectOther}</a>",
                    app=qAppName(),
                    tool=settings.getMergeToolName(),
                    settingsLink=makeInternalLink("prefs", PREFKEY_MERGETOOL),
                    selectOther=self.tr("Select another merge tool...")),

            "ours":
                self.tr("Reject incoming changes. "
                        "The file won’t be modified from its current state in HEAD."),

            "theirs":
                self.tr("Accept incoming changes. "
                        "The file will be <b>replaced</b> with the incoming version."),

            "dbutheirs":
                self.tr("Accept incoming changes. The file will be added back to your branch with the incoming changes."),

            "dbuours":
                self.tr("Reject incoming changes. The file won’t be added back to your branch."),

            "dbtours":
                self.tr("Reject incoming deletion. Our version of the file will be kept intact."),

            "dbttheirs":
                self.tr("Accept incoming deletion. The file will be deleted."),
        }
