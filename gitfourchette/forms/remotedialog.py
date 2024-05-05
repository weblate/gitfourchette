from gitfourchette.forms.brandeddialog import convertToBrandedDialog
from gitfourchette.forms.ui_remotedialog import Ui_RemoteDialog
from gitfourchette.qt import *
from gitfourchette.toolbox import *


class RemoteDialog(QDialog):
    def __init__(self, edit: bool, name: str, url: str, customKeyFile: str,
                 existingRemotes: list[str], parent: QWidget):

        super().__init__(parent)

        self.ui = Ui_RemoteDialog()
        self.ui.setupUi(self)

        okButton = self.ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok)

        self.ui.urlEdit.setText(url)
        self.ui.nameEdit.setText(name)
        self.existingRemotes = existingRemotes

        if not edit:
            self.ui.urlEdit.textChanged.connect(self.autoFillName)
            self.ui.nameEdit.textChanged.connect(self.onNameEdited)
            self.allowAutoFillName = True
        else:
            self.allowAutoFillName = False

        self.ui.keyFilePicker.makeFixedHeight()
        self.ui.keyFilePicker.setPath(customKeyFile)

        nameTaken = translate("NameValidationError", "This name is already taken by another remote.")
        cannotBeEmpty = translate("NameValidationError", "Cannot be empty.")

        validator = ValidatorMultiplexer(self)
        validator.setGatedWidgets(okButton)
        validator.connectInput(self.ui.nameEdit, lambda s: nameValidationMessage(s, existingRemotes, nameTaken))
        validator.connectInput(self.ui.urlEdit, lambda s: cannotBeEmpty if not s.strip() else "")

        if edit:
            title = self.tr("Edit remote {0}").format(hquoe(name))
            self.setWindowTitle(self.tr("Edit remote"))
            okButton.setText(self.tr("Save"))
            self.ui.fetchAfterAddCheckBox.setVisible(False)
        else:
            title = self.tr("Add remote")
            self.setWindowTitle(self.tr("Add remote"))
            okButton.setText(self.tr("Add"))
            self.ui.fetchAfterAddCheckBox.setVisible(True)

        convertToBrandedDialog(self, title)

        if not url and not edit:
            url = guessRemoteUrlFromText(QApplication.clipboard().text())
            self.ui.urlEdit.setText(url)
            self.ui.urlEdit.setFocus()

        validator.run(silenceEmptyWarnings=True)

    @property
    def privateKeyFilePath(self):
        return self.ui.keyFilePicker.privateKeyPath()

    def autoFillName(self, url: str):
        if not self.allowAutoFillName:
            return

        host, path = splitRemoteUrl(url)

        # Sanitize host
        for c in " ?/\\*~<>|:":
            host = host.replace(c, "_")

        # Clean up common host names (git.(...).org)
        host = host.removeprefix("git.")
        for tld in (".com", ".org", ".net"):
            if host.endswith(tld):
                host = host.removesuffix(tld)
                break

        host = withUniqueSuffix(host, self.existingRemotes)
        self.ui.nameEdit.setText(host)
        self.allowAutoFillName = True  # re-enable this since we got this far

    def onNameEdited(self, name: str):
        self.allowAutoFillName = name == ""
