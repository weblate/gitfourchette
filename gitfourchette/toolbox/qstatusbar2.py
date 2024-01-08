from gitfourchette.qt import *
from gitfourchette.toolbox import *


class QStatusBar2(QStatusBar):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("QStatusBar2")

        self.memoryIndicator = MemoryIndicator(self)

        self.setSizeGripEnabled(False)
        self.addPermanentWidget(self.memoryIndicator)
        # macOS: must reset stylesheet after addPermanentWidget for no-border thickness thing to take effect
        self.memoryIndicator.setStyleSheet(self.memoryIndicator.styleSheet())

        self.busyWidget = QWidget(self)
        self.busySpinner = QBusySpinner(self.busyWidget, centerOnParent=False)
        self.busySpinner.stop()
        self.busyLabel = QLabel(self.busyWidget)
        # Emojis such as the lightbulb may increase the label's height
        self.busyWidget.setMaximumHeight(self.fontMetrics().height())

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.busySpinner)
        layout.addWidget(self.busyLabel, 1)
        self.busyWidget.setLayout(layout)

        self.busyWidget.setVisible(False)

    # def showMessage(self, text: str, timeout=0):
    #     super().showMessage(text.upper(), timeout)

    def showBusyMessage(self, text: str):
        self.busyLabel.setText(text)
        if not self.busySpinner.isSpinning():
            self.busySpinner.start()
            self.busyWidget.setVisible(True)
            self.addWidget(self.busyWidget, 1)

    def clearMessage(self):
        # Temporary messages take precedence over busySpinner/busyWidget, so
        # those widgets might be invisible even though a message is set.
        # So, busySpinner.isSpinning is a better way to check that a message
        # is currently set than .isVisible.
        if self.busySpinner.isSpinning():
            self.busySpinner.stop()
            self.removeWidget(self.busyWidget)
            self.busyWidget.setVisible(False)
        super().clearMessage()

    def enableMemoryIndicator(self, show: bool = False):
        self.memoryIndicator.setVisible(show)
