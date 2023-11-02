from gitfourchette.qt import *
from gitfourchette.toolbox import *


class QStatusBar2(QStatusBar):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("QStatusBar2")

        self.memoryIndicator = MemoryIndicator(self)

        self.warningLabel = QLabel(self)
        self.warningLabel.setObjectName("statusWarning")  # for styling via QSS
        self.warningLabel.setText("warning")

        self.setSizeGripEnabled(False)
        self.addPermanentWidget(self.warningLabel)
        self.addPermanentWidget(self.memoryIndicator)
        # macOS: must reset stylesheet after addPermanentWidget for no-border thickness thing to take effect
        self.memoryIndicator.setStyleSheet(self.memoryIndicator.styleSheet())

        self.busyWidget = QWidget(self)
        self.busySpinner = QBusySpinner(self.busyWidget, centerOnParent=False)
        self.busySpinner.stop()
        self.busyLabel = QLabel(self.busyWidget)
        # Emojis such as the lightbulb may increase the label's height
        self.busyWidget.setMaximumHeight(self.fontMetrics().height())
        self.busyWidget.setVisible(False)

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.busySpinner)
        layout.addWidget(self.busyLabel, 1)
        self.busyWidget.setLayout(layout)

    # def showMessage(self, text: str, timeout=0):
    #     super().showMessage(text.upper(), timeout)

    def showBusyMessage(self, text: str):
        self.busyLabel.setText(text)
        self.busySpinner.start()
        if not self.busyWidget.isVisible():
            self.addWidget(self.busyWidget, 1)
            self.busyWidget.setVisible(True)

    def clearMessage(self):
        if self.busyWidget.isVisible():
            self.busySpinner.stop()
            self.removeWidget(self.busyWidget)
            self.busyWidget.setVisible(False)
        super().clearMessage()

    def showPermanentWarning(self, text: str):
        self.warningLabel.setVisible(bool(text))
        self.warningLabel.setText(text)

    def enableMemoryIndicator(self, show: bool = False):
        self.memoryIndicator.setVisible(show)
