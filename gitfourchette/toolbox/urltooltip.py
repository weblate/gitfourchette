# -----------------------------------------------------------------------------
# Copyright (C) 2024 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

from gitfourchette.qt import *


class UrlToolTip(QTimer):
    def __init__(self, parent):
        super().__init__(parent)
        self._pendingText = ""
        self.setInterval(QApplication.style().styleHint(QStyle.StyleHint.SH_ToolTip_WakeUpDelay))
        self.setSingleShot(True)
        self.timeout.connect(lambda: QToolTip.showText(QCursor.pos(), self._pendingText))

    def linkHovered(self, url: str):
        self._pendingText = url
        if QToolTip.isVisible():
            self.stop()
            self.timeout.emit()
        else:
            self.start()

    def install(self):
        parentWidget = self.parent()
        assert isinstance(parentWidget, QWidget)
        for label in parentWidget.findChildren(QLabel):
            if label.openExternalLinks():
                label.linkHovered.connect(self.linkHovered)
