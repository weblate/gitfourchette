from pathlib import Path

from gitfourchette.qt import *
from gitfourchette.remotelink import isPrivateKeyPassphraseProtected
from gitfourchette.toolbox import QFilePickerCheckBox, PersistentFileDialog, paragraphs


class KeyFilePickerCheckBox(QFilePickerCheckBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        filePickerTip = paragraphs(
            self.tr("{app} normally uses public/private keys in {path} to authenticate you with remote servers."),
            self.tr("Tick this box if you want to access this remote with a custom key.")).format(app=qAppName(), path="~/.ssh")
        self.checkBox.setToolTip(filePickerTip)

    def fileDialog(self):
        sshDir = Path("~/.ssh").expanduser()
        if not sshDir.exists():
            sshDir = ""

        prompt = self.tr("Select public key file for this remote")
        publicKeyFilter = self.tr("Public key file") + " (*.pub)"
        return PersistentFileDialog.openFile(self, "KeyFile", prompt, filter=publicKeyFilter, fallbackPath=str(sshDir))

    def validatePath(self, path: str):
        if not path:
            return ""

        p = Path(path)

        if not p.is_file():
            return self.tr("File not found.")

        if path.endswith(".pub"):
            privateKey = p.with_suffix("")
            if not privateKey.is_file():
                return self.tr("Accompanying private key not found.")
        else:
            privateKey = p
            if not privateKey.with_suffix(".pub").is_file():
                return self.tr("Accompanying public key not found.")

        if isPrivateKeyPassphraseProtected(str(privateKey)):
            return self.tr("{app} doesn’t support passphrase-protected private keys yet.").format(app=qAppName())

        return ""

    def privateKeyPath(self):
        return self.path().removesuffix(".pub")
