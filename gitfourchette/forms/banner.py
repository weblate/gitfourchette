from contextlib import suppress
from typing import Callable

from gitfourchette.qt import *
from gitfourchette.toolbox import *


HORIZONTAL_CONTENT_HEIGHT = 24
FONT_POINT_PERCENT = 90


class Banner(QFrame):
    def __init__(self, parent, orientation: Qt.Orientation):
        super().__init__(parent)
        self.setObjectName("StateBox")

        icon = QLabel(self)
        icon.setPixmap(stockIcon("SP_MessageBoxInformation").pixmap(HORIZONTAL_CONTENT_HEIGHT))

        label = QLabel(__name__, self)
        label.setWordWrap(True)

        button = QToolButton(self)
        button.setText(self.tr("Abort"))

        dismissButton = QToolButton(self)
        dismissButton.setText(self.tr("Dismiss", "clicking the Dismiss button will make the info banner disappear"))
        dismissButton.clicked.connect(self.dismiss)
        dismissButton.clicked.connect(self.hide)

        if orientation == Qt.Orientation.Vertical:
            layout = QVBoxLayout(self)
        else:
            label.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Minimum)
            layout = QHBoxLayout(self)

        layout.setContentsMargins(0,0,0,0)
        # layout.setSpacing(0)
        layout.addWidget(icon)
        layout.addWidget(label)
        layout.addWidget(button)
        layout.addWidget(dismissButton)

        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)

        if orientation == Qt.Orientation.Horizontal:
            for b in button, dismissButton:
                tweakWidgetFont(b, FONT_POINT_PERCENT)
                b.setMaximumHeight(HORIZONTAL_CONTENT_HEIGHT)

        self.icon = icon
        self.label = label
        self.button = button
        self.dismissButton = dismissButton
        self.lastWarningWasDismissed = False
        self.orientation = orientation

    def popUp(
            self,
            title: str,
            text: str,
            heeded=False,
            canDismiss=False,
            withIcon=False,
            buttonLabel: str = "",
            buttonCallback: Callable = None
    ):
        self.setProperty("heeded", str(heeded).lower())
        self.setStyleSheet("* {}")  # reset stylesheet to percolate property change

        smallPt = adjustedWidgetFontSize(self.label, FONT_POINT_PERCENT)
        markup = f"<style>sm {{ font-size: {smallPt}pt; }}</style>"
        if title:
            markup += f"<b>{title}</b>"
            if text:
                markup += f"<br><sm>{text}</sm>"
        else:
            markup += f"<sm>{text}</sm>"

        self.label.setTextFormat(Qt.TextFormat.RichText)
        self.label.setText(markup)
        self.icon.setVisible(withIcon)

        self.dismissButton.setVisible(canDismiss)
        self.lastWarningWasDismissed = False

        # Always disconnect any previous callback
        with suppress(BaseException):
            self.button.clicked.disconnect()

        if not buttonLabel:
            assert not buttonCallback
            self.button.setVisible(False)
        else:
            assert buttonCallback
            self.button.setVisible(True)
            self.button.setText(buttonLabel)
            self.button.clicked.connect(buttonCallback)

        self.setVisible(True)

    def dismiss(self):
        self.lastWarningWasDismissed = True
        self.hide()
