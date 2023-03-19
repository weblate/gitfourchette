"""
TODO: Remove this once libgit2 1.6 support lands in pygit2
"""


from gitfourchette.qt import *
from gitfourchette.widgets.brandeddialog import convertToBrandedDialog
from gitfourchette.widgets.ui_stashdialog_legacy import Ui_StashDialog_Legacy


class StashDialog_Legacy(QDialog):
    def __init__(self, parent):
        super().__init__(parent)

        self.ui = Ui_StashDialog_Legacy()
        self.ui.setupUi(self)

        convertToBrandedDialog(self)

