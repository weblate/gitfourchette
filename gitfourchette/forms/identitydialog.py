from gitfourchette.forms.brandeddialog import convertToBrandedDialog
from gitfourchette.forms.signatureform import SignatureForm
from gitfourchette.forms.ui_identitydialog import Ui_IdentityDialog
from gitfourchette.porcelain import get_git_global_identity
from gitfourchette.qt import *
from gitfourchette.toolbox import *


class IdentityDialog(QDialog):
    def __init__(self, repo, firstRun, parent):
        super().__init__(parent)

        ui = Ui_IdentityDialog()
        ui.setupUi(self)
        self.ui = ui
        ui.warningLabel.setVisible(repo.has_local_identity())

        # Initialize with global identity values (if any)
        initialName, initialEmail = get_git_global_identity()
        ui.nameEdit.setText(initialName)
        ui.emailEdit.setText(initialEmail)

        validator = ValidatorMultiplexer(self)
        validator.setGatedWidgets(ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok))
        validator.connectInput(ui.nameEdit, SignatureForm.validateInput)
        validator.connectInput(ui.emailEdit, SignatureForm.validateInput)
        validator.run(silenceEmptyWarnings=True)

        subtitle = translate("IdentityDialog", "This information will be embedded in the commits and tags that you create on this machine.")
        if firstRun:
            subtitle = translate("IdentityDialog", "Before editing this repository, please set up your identity for Git.") + " " + subtitle

        convertToBrandedDialog(self, subtitleText=subtitle, multilineSubtitle=True)

    def identity(self) -> tuple[str, str]:
        name = self.ui.nameEdit.text()
        email = self.ui.emailEdit.text()
        return name, email
