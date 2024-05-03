from gitfourchette.qt import *
from gitfourchette.toolbox import *
from gitfourchette.forms.ui_openrepoprogress import Ui_OpenRepoProgress


class OpenRepoProgress(QWidget):
    def __init__(self, parent=None, name=""):
        super().__init__(parent)
        self.ui = Ui_OpenRepoProgress()
        self.ui.setupUi(self)

        abortIcon = stockIcon("SP_BrowserStop")

        self.ui.abortButton.setIcon(abortIcon)
        self.ui.abortButton.setEnabled(False)

        if name:
            self.initialMessage = self.tr("Opening {0}...").format(tquo(name))
            self.ui.label.setText(self.initialMessage)
        else:
            self.initialMessage = self.ui.label.text()

    def reset(self):
        self.ui.retranslateUi(self)
        self.ui.label.setText(self.initialMessage)
        self.ui.progressBar.setRange(0, 100)
        self.ui.progressBar.setValue(0)
