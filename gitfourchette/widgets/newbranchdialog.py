from gitfourchette.qt import *
from gitfourchette.widgets.brandeddialog import convertToBrandedDialog
from gitfourchette.widgets.ui_newbranchdialog import Ui_NewBranchDialog
from gitfourchette.util import labelQuote
from gitfourchette import porcelain


class NewBranchDialog(QDialog):
    def __init__(
            self,
            initialName: str,
            target: str,
            targetSubtitle: str = "",
            trackingCandidates: list[str] = [],
            forbiddenBranchNames: list[str] = [],
            parent=None):

        super().__init__(parent)

        self.forbiddenBranchNames = forbiddenBranchNames

        self.ui = Ui_NewBranchDialog()
        self.ui.setupUi(self)

        self.ui.nameEdit.textChanged.connect(self.onBranchNameChanged)
        self.ui.nameEdit.setText(initialName)

        self.ui.trackRemoteBranchCheckBox.setChecked(False)  # TODO: emit signal to disable the combobox
        self.ui.trackRemoteBranchCheckBox.setVisible(False)  # TODO: For now, tracking branch selection isn't implemented
        self.ui.trackRemoteBranchComboBox.setVisible(False)

        convertToBrandedDialog(self, f"New branch", f"Commit at tip: {target}\n“{targetSubtitle}”")

        self.onBranchNameChanged()  # do initial validation

        self.ui.nameEdit.setFocus()
        self.ui.nameEdit.selectAll()

    @property
    def acceptButton(self):
        return self.ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok)

    def onBranchNameChanged(self):
        newBranchName = self.ui.nameEdit.text()
        error = ""

        try:
            porcelain.validateBranchName(newBranchName)
            if newBranchName in self.forbiddenBranchNames:
                error = "Already taken by another local branch."
        except ValueError as exc:
            error = str(exc)

        self.ui.nameValidationText.setText(error)
        self.acceptButton.setEnabled(error == "")
