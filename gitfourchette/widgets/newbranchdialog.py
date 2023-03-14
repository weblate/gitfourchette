from gitfourchette.qt import *
from gitfourchette.toolbox import *
from gitfourchette.widgets.brandeddialog import convertToBrandedDialog
from gitfourchette.widgets.ui_newbranchdialog import Ui_NewBranchDialog
from gitfourchette import porcelain
from gitfourchette import util
import typing


def validateBranchName(newBranchName: str, reservedNames: list[str], nameInUseMessage: str) -> str:
    try:
        porcelain.validateBranchName(newBranchName)
    except porcelain.NameValidationError as exc:
        return util.translateNameValidationError(exc)

    if newBranchName in reservedNames:
        return nameInUseMessage

    return ""  # validation passed, no error


class NewBranchDialog(QDialog):
    def __init__(
            self,
            initialName: str,
            target: str,
            targetSubtitle: str,
            upstreams: list[str],
            reservedNames: list[str],
            parent=None):

        super().__init__(parent)

        self.ui = Ui_NewBranchDialog()
        self.ui.setupUi(self)

        self.ui.nameEdit.setText(initialName)

        self.ui.upstreamComboBox.addItems(upstreams)

        # hack to trickle down initial 'toggled' signal to combobox
        self.ui.upstreamCheckBox.setChecked(True)
        self.ui.upstreamCheckBox.setChecked(False)

        if not upstreams:
            self.ui.upstreamCheckBox.setChecked(False)
            self.ui.upstreamCheckBox.setVisible(False)
            self.ui.upstreamComboBox.setVisible(False)

        reservedMessage = self.tr("Name already taken by another local branch.")

        def validateNewBranchName(name: str):
            return validateBranchName(name, reservedNames, reservedMessage)

        validator = ValidatorMultiplexer(self)
        validator.setGatedWidgets(self.acceptButton)
        validator.connectInput(self.ui.nameEdit, validateNewBranchName)
        validator.run()

        convertToBrandedDialog(self, self.tr("New branch"), self.tr("Commit at tip:") + f" {target}\n“{targetSubtitle}”")

        self.ui.nameEdit.setFocus()
        self.ui.nameEdit.selectAll()

    @property
    def acceptButton(self):
        return self.ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok)
