from allqt import *
from widgets.brandeddialog import convertToBrandedDialog
from widgets.ui_remotedialog import Ui_RemoteDialog
from util import labelQuote


class RemoteDialog(QDialog):
    def __init__(
            self,
            remoteName: str,
            remoteURL: str,
            parent):

        super().__init__(parent)

        self.ui = Ui_RemoteDialog()
        self.ui.setupUi(self)

        self.ui.nameEdit.setText(remoteName)
        self.ui.urlEdit.setText(remoteURL)

        convertToBrandedDialog(self, F"Edit remote {labelQuote(remoteName)}")

        self.setMaximumHeight(self.height())
