import contextlib
from typing import Callable

from gitfourchette.qt import *


class StateBox(QFrame):
    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("StateBox")

        label = QLabel(__name__, self)
        label.setWordWrap(True)

        button = QPushButton(self.tr("Abort..."), self)

        layout = QVBoxLayout()
        layout.setContentsMargins(0,0,0,0)
        # layout.setSpacing(0)
        layout.addWidget(label)
        layout.addWidget(button)
        self.setLayout(layout)

        self.label = label
        self.button = button

    def showPermanentWarning(self, title: str, text: str, heeded: bool = False):
        self.setProperty("heeded", str(heeded).lower())
        self.setStyleSheet("* {}")  # reset stylesheet to percolate property change

        self.label.setText(f"<b>{title.upper()}</b><br><small>{text}</small>")

    def setButton(self, label: str | None = "", callback: Callable = None):
        # Always disconnect any previous callback
        with contextlib.suppress(BaseException):
            self.button.clicked.disconnect()

        if not label:
            assert not callback
            self.button.setVisible(False)
        else:
            assert callback
            self.button.setVisible(True)
            self.button.setText(label)
            self.button.clicked.connect(callback)