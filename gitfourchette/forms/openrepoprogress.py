from gitfourchette.qt import *
from gitfourchette.toolbox import *
from gitfourchette.forms.ui_openrepoprogress import Ui_OpenRepoProgress


class OpenRepoProgress(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ui = Ui_OpenRepoProgress()
        self.ui.setupUi(self)

        abortIcon = stockIcon(QStyle.StandardPixmap.SP_BrowserStop)
        self.ui.abortButton.setIcon(abortIcon)

    def reset(self):
        self.ui.retranslateUi(self)
        self.ui.progressBar.setRange(0, 100)
        self.ui.progressBar.setValue(0)
