from ..qt import *
from .brandeddialog import convertToBrandedDialog
from .ui_stashdialog import Ui_StashDialog


class StashDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)

        self.ui = Ui_StashDialog()
        self.ui.setupUi(self)

        convertToBrandedDialog(self)

