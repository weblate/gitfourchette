from gitfourchette.forms.brandeddialog import convertToBrandedDialog
from gitfourchette.forms.ui_remotedialog import Ui_RemoteDialog
from gitfourchette.qt import *
from gitfourchette.toolbox import *


class RemoteDialog(QDialog):
    def __init__(
            self,
            edit: bool,
            remoteName: str,
            remoteURL: str,
            customKeyFile: str,
            existingRemotes: list[str],
            parent: QWidget):

        super().__init__(parent)

        self.ui = Ui_RemoteDialog()
        self.ui.setupUi(self)

        okButton = self.ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok)

        self.ui.nameEdit.setText(remoteName)
        self.ui.urlEdit.setText(remoteURL)

        self.ui.keyFilePicker.makeFixedHeight()
        self.ui.keyFilePicker.setPath(customKeyFile)

        nameTaken = translate("NameValidationError", "This name is already taken by another remote.")
        cannotBeEmpty = translate("NameValidationError", "Cannot be empty.")

        validator = ValidatorMultiplexer(self)
        validator.setGatedWidgets(okButton)
        validator.connectInput(self.ui.nameEdit, lambda s: nameValidationMessage(s, existingRemotes, nameTaken))
        validator.connectInput(self.ui.urlEdit, lambda s: cannotBeEmpty if not s.strip() else "")

        if edit:
            title = self.tr("Edit remote {0}").format(hquoe(remoteName))
            self.setWindowTitle(self.tr("Edit remote"))
            okButton.setText(self.tr("Save"))
            self.ui.fetchAfterAddCheckBox.setVisible(False)
        else:
            title = self.tr("Add remote")
            self.setWindowTitle(self.tr("Add remote"))
            okButton.setText(self.tr("Add"))
            self.ui.fetchAfterAddCheckBox.setVisible(True)

        convertToBrandedDialog(self, title)

        validator.run()

    @property
    def privateKeyFilePath(self):
        return self.ui.keyFilePicker.privateKeyPath()
