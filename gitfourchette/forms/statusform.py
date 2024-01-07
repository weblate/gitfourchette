import logging

from gitfourchette.qt import *
from gitfourchette.forms.ui_statusform import Ui_StatusForm

logger = logging.getLogger(__name__)


class StatusForm(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.ui = Ui_StatusForm()
        self.ui.setupUi(self)

        self.ui.progressBar.setMinimum(0)
        self.ui.progressBar.setMaximum(0)
        self.ui.progressBar.setValue(0)

        self.setBlurb("")

    def setBlurb(self, text: str):
        self.ui.stackedWidget.setCurrentWidget(self.ui.blurbPage)
        self.ui.blurbLabel.setText(text)

    def initProgress(self, text: str):
        self.ui.stackedWidget.setCurrentWidget(self.ui.progressPage)
        self.ui.linkMessage.setText(text)
        self.ui.progressBar.setMinimum(0)
        self.ui.progressBar.setMaximum(0)
        self.ui.progressBar.setValue(0)

    def setProgressValue(self, value: int, maximum: int):
        self.ui.progressBar.setValue(value)
        self.ui.progressBar.setMaximum(maximum)

    def setProgressMessage(self, message: str):
        if message.startswith("Sideband"):
            logger.info(f"Sideband >{message.encode('utf-8', errors='ignore')}<")
        self.ui.linkMessage.setText(message)
