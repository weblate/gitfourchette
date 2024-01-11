import contextlib
from typing import Callable

from gitfourchette.qt import *
from gitfourchette.toolbox import *


class Banner(QFrame):
    def __init__(self, parent, orientation: Qt.Orientation):
        super().__init__(parent)
        self.setObjectName("StateBox")

        icon = QLabel(self)
        icon.setPixmap(stockIcon(QStyle.StandardPixmap.SP_MessageBoxInformation).pixmap(16))

        label = QLabel(__name__, self)
        label.setWordWrap(True)

        button = QToolButton(self)
        button.setText(self.tr("Abort"))

        dismissButton = QToolButton(self)
        dismissButton.setText(self.tr("Dismiss"))
        dismissButton.clicked.connect(self.dismiss)
        dismissButton.clicked.connect(self.hide)

        if orientation == Qt.Orientation.Vertical:
            layout = QVBoxLayout()
        else:
            label.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Minimum)
            layout = QHBoxLayout()

        layout.setContentsMargins(0,0,0,0)
        # layout.setSpacing(0)
        layout.addWidget(icon)
        layout.addWidget(label)
        layout.addWidget(button)
        layout.addWidget(dismissButton)
        self.setLayout(layout)

        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)

        self.icon = icon
        self.label = label
        self.button = button
        self.dismissButton = dismissButton
        self.lastWarningWasDismissed = False

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

        markup = ""
        if title:
            markup += f"<b>{title.upper()}</b>"
            if text:
                markup += f"<br><small>{text}</small>"
        else:
            markup = f"<small>{text}</small>"

        self.label.setText(markup)
        self.icon.setVisible(withIcon)

        self.dismissButton.setVisible(canDismiss)
        self.lastWarningWasDismissed = False

        # Always disconnect any previous callback
        with contextlib.suppress(BaseException):
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
