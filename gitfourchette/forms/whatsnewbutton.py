# -----------------------------------------------------------------------------
# Copyright (C) 2026 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

import logging

from gitfourchette import settings, colors
from gitfourchette.localization import _
from gitfourchette.qt import *
from gitfourchette.toolbox import ActionDef, stockIcon, mixColors

logger = logging.getLogger(__name__)


class WhatsNewButton(QToolButton):
    showChangelog = Signal()

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        vName = "v" + APP_VERSION

        self.setObjectName("WhatsNewButton")
        self.setIcon(stockIcon("SP_MessageBoxInformation"))
        self.setIcon(stockIcon("gitfourchette"))
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setText(" " + _("{app} was updated to {version}", app=APP_DISPLAY_NAME, version=vName))

        actions = [
            ActionDef(_("Welcome back!"), kind=ActionDef.Kind.Section),
            ActionDef(_("What’s New in {version}", version=vName), self.showWhatsNew, icon="gitfourchette"),
            ActionDef.SEPARATOR,
            ActionDef(_("Show this button after the next update"), self.neverShowAgain, checkState=1),
            ActionDef(_("Dismiss"), self.dismiss),
        ]

        color1 = mixColors(self.palette().window().color(), colors.yellow, .8)
        color2 = colors.black
        self.setStyleSheet(f"QToolButton {{ background-color: {color1.name()}; color: {color2.name()}; padding: 0 1em 0 1em; }}")

        self.setMenu(ActionDef.makeQMenu(self, actions))

    def showWhatsNew(self):
        self.showChangelog.emit()

    def neverShowAgain(self):
        key = self.__class__.__name__
        try:
            settings.prefs.dontShowAgain.remove(key)
        except ValueError:
            settings.prefs.dontShowAgain.append(key)
        settings.prefs.setDirty()

    def dismiss(self):
        self.deleteLater()
