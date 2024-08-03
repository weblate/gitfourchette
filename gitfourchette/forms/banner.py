from typing import Callable

from gitfourchette.qt import *
from gitfourchette.toolbox import *


HORIZONTAL_CONTENT_HEIGHT = 20
FONT_POINT_PERCENT = 90
PERMANENT_PROPERTY = "permanent"


class Banner(QFrame):
    buttons: list[QToolButton]

    def __init__(self, parent, orientation: Qt.Orientation):
        super().__init__(parent)
        self.setObjectName("Banner")

        icon = QLabel(self)
        icon.setPixmap(stockIcon("SP_MessageBoxInformation").pixmap(min(16, HORIZONTAL_CONTENT_HEIGHT)))

        label = QLabel(__name__, self)
        label.setWordWrap(True)

        if orientation == Qt.Orientation.Vertical:
            layout = QVBoxLayout(self)
        else:
            label.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Minimum)
            layout = QHBoxLayout(self)

        layout.setContentsMargins(QMargins())
        layout.addWidget(icon)
        layout.addWidget(label)

        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)

        self.icon = icon
        self.label = label
        self.lastWarningWasDismissed = False
        self.orientation = orientation
        self.buttons = []

        self.dismissButton = self.addButton(self.tr("Dismiss"), self.dismiss, permanent=True)

    def addButton(self, text: str, callback: Callable = None, permanent=False) -> QToolButton:
        button = QToolButton(self)
        button.setText(text)
        button.setProperty(PERMANENT_PROPERTY, "true" if permanent else "")
        button.setAutoRaise(True)
        self.buttons.append(button)

        if callback:
            button.clicked.connect(callback)

        layout: QHBoxLayout = self.layout()
        layout.insertWidget(2, button)

        if self.orientation == Qt.Orientation.Horizontal:
            tweakWidgetFont(button, FONT_POINT_PERCENT)
            button.setMaximumHeight(HORIZONTAL_CONTENT_HEIGHT)

        return button

    def clearButtons(self):
        for i in range(len(self.buttons) - 1, -1, -1):
            button = self.buttons[i]
            if not button.property(PERMANENT_PROPERTY):
                button.hide()
                button.deleteLater()
                del self.buttons[i]

    def popUp(self, title: str, text: str, heeded=False, canDismiss=False, withIcon=False):
        self.clearButtons()
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

        self.setVisible(True)

    def dismiss(self):
        self.lastWarningWasDismissed = True
        self.hide()
        self.clearButtons()
