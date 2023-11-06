from gitfourchette import exttools
from gitfourchette.qt import *
from gitfourchette.toolbox import *
from gitfourchette.forms.brandeddialog import convertToBrandedDialog
from gitfourchette.forms.ui_remotedialog import Ui_RemoteDialog
import os


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

        # self.ui.keyFileBrowseButton.setIcon(util.stockIcon(QStyle.StandardPixmap.SP_DialogOpenButton))
        self.ui.keyFileBrowseButton.clicked.connect(self.browseKeyFile)

        hasCustomKeyFile = bool(customKeyFile)
        self.ui.keyFilePathEdit.setText(customKeyFile)

        self.ui.keyFileGroupBox.setToolTip(paragraphs(
            self.tr("{0} normally uses public/private keys in ~/.ssh "
                    "to authenticate you with remote servers.").format(qAppName()),
            self.tr("Tick this box if you want to access this remote with a custom key.")))

        self.ui.keyFileGroupBox.setChecked(hasCustomKeyFile)
        self.ui.keyFileGroupBox.toggled.emit(hasCustomKeyFile)  # fire signal once to enable/disable fields appropriately
        self.ui.keyFileGroupBox.toggled.connect(self.autoBrowseKeyFile)

        nameTaken = translate("NameValidationError", "This name is already taken by another remote.")
        cannotBeEmpty = translate("NameValidationError", "Cannot be empty.")

        validator = ValidatorMultiplexer(self)
        validator.setGatedWidgets(okButton)
        validator.connectInput(self.ui.nameEdit, lambda s: nameValidationMessage(s, existingRemotes, nameTaken))
        validator.connectInput(self.ui.urlEdit, lambda s: cannotBeEmpty if not s.strip() else "")
        validator.connectInput(self.ui.keyFilePathEdit, self.validateKeyFileInput, mustBeValid=False)

        if edit:
            title = self.tr("Edit remote “{0}”").format(escape(elide(remoteName)))
            self.setWindowTitle(self.tr("Edit remote"))
            okButton.setText(self.tr("Save changes"))
            self.ui.fetchAfterAddCheckBox.setVisible(False)
        else:
            title = self.tr("Add remote")
            self.setWindowTitle(self.tr("Add remote"))
            okButton.setText(self.tr("Add remote"))
            self.ui.fetchAfterAddCheckBox.setVisible(True)

        convertToBrandedDialog(self, title)

        validator.run()

    @property
    def privateKeyFilePath(self):
        if not self.ui.keyFileGroupBox.isChecked():
            return ""

        path = self.ui.keyFilePathEdit.text()
        return path.removesuffix(".pub")

    def validateKeyFileInput(self, path: str):
        if not os.path.isfile(path):
            return self.tr("File not found.")

        if path.endswith(".pub"):
            if not os.path.isfile(path.removesuffix(".pub")):
                return self.tr("Accompanying private key not found.")
        else:
            if not os.path.isfile(path + ".pub"):
                return self.tr("Accompanying public key not found.")

        return ""

    def autoBrowseKeyFile(self):
        """
        If checkbox is ticked and path is empty, bring up file browser.
        """
        if self.ui.keyFileGroupBox.isChecked() and not self.ui.keyFilePathEdit.text().strip():
            self.browseKeyFile()

    def browseKeyFile(self):
        sshDir = os.path.expanduser("~/.ssh")
        if not os.path.exists(sshDir):
            sshDir = ""

        qfd = PersistentFileDialog.openFile(
            self, "KeyFile", self.tr("Select public key file for remote “{0}”").format(self.ui.nameEdit.text()),
            filter=self.tr("Public key file") + " (*.pub)",
            fallbackPath=sshDir)

        def onReject():
            # File browser canceled and lineedit empty, untick checkbox
            if not self.ui.keyFilePathEdit.text().strip():
                self.ui.keyFileGroupBox.setChecked(False)

        qfd.fileSelected.connect(self.ui.keyFilePathEdit.setText)
        qfd.rejected.connect(onReject)
        qfd.show()
