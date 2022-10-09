from gitfourchette.qt import *
from gitfourchette.widgets.brandeddialog import convertToBrandedDialog
from gitfourchette.widgets.ui_newbranchdialog import Ui_NewBranchDialog
from gitfourchette.util import labelQuote


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

    @property
    def acceptButton(self):
        return self.ui.buttonBox.button(QDialogButtonBox.Ok)

    def onBranchNameChanged(self):
        newBranchName = self.ui.nameEdit.text()
        error = ""

        if not newBranchName:
            error = "Cannot be empty."
        elif newBranchName == '@':
            error = "Illegal name."
        elif any(c in " ~^:[?*\\" for c in newBranchName):
            error = "Contains a forbidden character."
        elif any(seq in newBranchName for seq in ["..", "//", "@{", "/.", ".lock/"]):
            error = "Contains a forbidden character sequence."
        elif newBranchName.startswith("."):
            error = "Illegal prefix."
        elif newBranchName.endswith(".lock"):
            error = "Illegal suffix."
        elif newBranchName in self.forbiddenBranchNames:
            error = "Already taken by another local branch."

        self.ui.nameValidationText.setText(error)
        self.acceptButton.setEnabled(error == "")

