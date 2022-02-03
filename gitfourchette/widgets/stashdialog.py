from allqt import *
from widgets.brandeddialog import convertToBrandedDialog
from widgets.ui_stashdialog import Ui_StashDialog


class StashDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)

        self.ui = Ui_StashDialog()
        self.ui.setupUi(self)

        convertToBrandedDialog(self)

