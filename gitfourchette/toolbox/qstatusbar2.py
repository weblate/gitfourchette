import contextlib
import typing

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

        self.generalPurposeButton = QToolButton(self)
        self.generalPurposeButton.setText("Action")
        self.generalPurposeButton.setMaximumHeight(self.fontMetrics().height())

        self.setSizeGripEnabled(False)
        self.addPermanentWidget(self.warningLabel)
        self.addPermanentWidget(self.generalPurposeButton)
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
        self.warningLabel.setVisible(False)
        self.generalPurposeButton.setVisible(False)

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

    def showPermanentWarning(self, text: str, heeded: bool = False):
        self.warningLabel.setProperty("heeded", str(heeded).lower())
        self.warningLabel.setStyleSheet("* {}")  # reset stylesheet to percolate property change

        self.warningLabel.setVisible(bool(text))
        self.warningLabel.setText(text)

    def enableMemoryIndicator(self, show: bool = False):
        self.memoryIndicator.setVisible(show)

    def setButton(self, label: str | None = "", callback: typing.Callable = None):
        # Always disconnect any previous callback
        with contextlib.suppress(BaseException):
            self.generalPurposeButton.clicked.disconnect()

        if not label:
            assert not callback
            self.generalPurposeButton.setVisible(False)
        else:
            assert callback
            self.generalPurposeButton.setVisible(True)
            self.generalPurposeButton.setText(label)
            self.generalPurposeButton.clicked.connect(callback)
