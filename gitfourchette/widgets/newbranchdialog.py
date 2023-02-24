from gitfourchette.qt import *
from gitfourchette.widgets.brandeddialog import convertToBrandedDialog
from gitfourchette.widgets.ui_newbranchdialog import Ui_NewBranchDialog
from gitfourchette import porcelain
from gitfourchette import util
import typing


def translateBranchNameValidationError(e: porcelain.BranchNameValidationError):
    E = porcelain.BranchNameValidationError
    errorDescriptions = {
        E.ILLEGAL_NAME: translate("BranchNameValidation", "Illegal name."),
        E.ILLEGAL_SUFFIX: translate("BranchNameValidation", "Illegal suffix."),
        E.ILLEGAL_PREFIX: translate("BranchNameValidation", "Illegal prefix."),
        E.CONTAINS_ILLEGAL_SEQ: translate("BranchNameValidation", "Contains illegal character sequence."),
        E.CONTAINS_ILLEGAL_CHAR: translate("BranchNameValidation", "Contains illegal character."),
        E.CANNOT_BE_EMPTY: translate("BranchNameValidation", "Cannot be empty."),
    }
    return errorDescriptions.get(e.code, "Branch name validation error {0}".format(e.code))


def validateLocalBranchName(newBranchName: str, forbiddenBranchNames: list[str]) -> str:
    try:
        porcelain.validateBranchName(newBranchName)
    except porcelain.BranchNameValidationError as exc:
        return translateBranchNameValidationError(exc)

    if newBranchName in forbiddenBranchNames:
        return translate("BranchNameValidation", "Name already taken by another local branch.")

    return ""  # validation passed, no error


class NewBranchDialog(QDialog):
    def __init__(
            self,
            initialName: str,
            target: str,
            targetSubtitle: str,
            upstreams: list[str],
            forbiddenBranchNames: list[str],
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

        util.installLineEditCustomValidator(
            validatorFunc=lambda name: validateLocalBranchName(name, forbiddenBranchNames),
            errorLabel=self.ui.nameValidationText,
            lineEdit=self.ui.nameEdit,
            gatedWidgets=[self.acceptButton])

        convertToBrandedDialog(self, self.tr("New branch"), self.tr("Commit at tip:") + f" {target}\n“{targetSubtitle}”")

        self.ui.nameEdit.setFocus()
        self.ui.nameEdit.selectAll()

    @property
    def acceptButton(self):
        return self.ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok)
