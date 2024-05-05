import logging

from gitfourchette.qt import *

logger = logging.getLogger(__name__)


class StatusForm(QStackedWidget):
    def __init__(self, parent):
        super().__init__(parent)

        self.blurbLabel = QLabel("")
        self.blurbLabel.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.blurbLabel.setWordWrap(True)
        self.blurbLabel.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse|Qt.TextInteractionFlag.TextSelectableByMouse)
        blurbPage = QScrollArea()
        blurbPage.setWidget(self.blurbLabel)
        blurbPage.setFrameShape(QFrame.Shape.NoFrame)
        blurbPage.setWidgetResizable(True)
        blurbPage.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.progressMessage = QLabel("Line1\nLine2")
        self.progressMessage.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.progressMessage.setWordWrap(True)
        self.progressBar = QProgressBar()
        progressPage = QWidget()
        progressLayout = QVBoxLayout(progressPage)
        progressLayout.addWidget(self.progressMessage)
        progressLayout.addWidget(self.progressBar)

        self.blurbLabel.setContentsMargins(4,4,4,4)
        progressLayout.setContentsMargins(4,4,4,4)

        self.addWidget(blurbPage)
        self.addWidget(progressPage)

    def setBlurb(self, text: str):
        self.setCurrentIndex(0)
        self.blurbLabel.setText(text)

    def initProgress(self, text: str):
        self.setCurrentIndex(1)
        self.progressMessage.setText(text)
        self.progressBar.setMinimum(0)
        self.progressBar.setMaximum(0)
        self.progressBar.setValue(0)

    def setProgressValue(self, value: int, maximum: int):
        self.progressBar.setValue(value)
        self.progressBar.setMaximum(maximum)

    def setProgressMessage(self, message: str):
        if message.startswith("Sideband"):
            logger.info(f"Sideband >{message.encode('utf-8', errors='ignore')}<")
        self.progressMessage.setText(message)
