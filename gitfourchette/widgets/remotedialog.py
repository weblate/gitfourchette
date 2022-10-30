from gitfourchette.qt import *
from gitfourchette.widgets.brandeddialog import convertToBrandedDialog
from gitfourchette.widgets.ui_remotedialog import Ui_RemoteDialog
from gitfourchette.util import escamp


class RemoteDialog(QDialog):
    def __init__(
            self,
            edit: bool,
            remoteName: str,
            remoteURL: str,
            parent):

        super().__init__(parent)

        self.ui = Ui_RemoteDialog()
        self.ui.setupUi(self)

        self.ui.nameEdit.setText(remoteName)
        self.ui.urlEdit.setText(remoteURL)

        if edit:
            title = self.tr("Edit remote “{0}”").format(escamp(remoteName))
            self.setWindowTitle(self.tr("Edit remote"))
        else:
            title = self.tr("Add remote")
            self.setWindowTitle(self.tr("Add remote"))
        self.setWindowTitle(title)
        convertToBrandedDialog(self, title)

        self.setMaximumHeight(self.height())
