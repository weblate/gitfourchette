# -----------------------------------------------------------------------------
# Copyright (C) 2026 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

from gitfourchette.qt import *


class QLabelExternalLinkToolTips(QTimer):
    """
    Shows tooltips when external hyperlinks are hovered in rich-text QLabels.
    """

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self._pendingText = ""
        self.setInterval(QApplication.style().styleHint(QStyle.StyleHint.SH_ToolTip_WakeUpDelay))
        self.setSingleShot(True)
        self.timeout.connect(lambda: QToolTip.showText(QCursor.pos(), self._pendingText))

        numLabels = 0
        for label in parent.findChildren(QLabel):
            if label.openExternalLinks():
                label.linkHovered.connect(self.linkHovered)
                numLabels += 1

        if not numLabels:
            raise NotImplementedError("didn't find any QLabels with openExternalLinks")

    def linkHovered(self, url: str):
        self._pendingText = url
        if QToolTip.isVisible():
            self.stop()
            self.timeout.emit()
        else:
            self.start()
