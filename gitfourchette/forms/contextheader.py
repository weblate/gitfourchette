# -----------------------------------------------------------------------------
# Copyright (C) 2024 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

from collections.abc import Callable

from gitfourchette.application import GFApplication
from gitfourchette.nav import NavLocator, NavContext
from gitfourchette.qt import *
from gitfourchette.tasks import *
from gitfourchette.toolbox import *

PERMANENT_PROPERTY = "permanent"


class ContextHeader(QFrame):
    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("ContextHeader")
        self.locator = NavLocator()
        self.buttons = []

        layout = QHBoxLayout(self)
        self.setMinimumHeight(24)

        self.mainLabel = QElidedLabel(self)

        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.mainLabel)

        self.maximizeButton = self.addButton(self.tr("Maximize"), permanent=True)
        self.maximizeButton.setIcon(stockIcon("maximize"))
        self.maximizeButton.setToolTip(self.tr("Maximize the diff area and hide the commit graph"))
        self.maximizeButton.setCheckable(True)

        self.restyle()
        GFApplication.instance().restyle.connect(self.restyle)

    def restyle(self):
        bg = mutedTextColorHex(self, .07)
        fg = mutedTextColorHex(self, .8)
        self.setStyleSheet(f"ContextHeader {{ background-color: {bg}; }}  ContextHeader QLabel {{ color: {fg}; }}")

    def addButton(self, text: str, callback: Callable | None = None, permanent=False) -> QToolButton:
        button = QToolButton(self)
        button.setText(text)
        button.setProperty(PERMANENT_PROPERTY, "true" if permanent else "")
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setAutoRaise(True)
        self.buttons.append(button)

        if callback is not None:
            button.clicked.connect(callback)

        layout: QHBoxLayout = self.layout()
        layout.insertWidget(1, button)

        button.setMaximumHeight(24)

        return button

    def clearButtons(self):
        for i in range(len(self.buttons) - 1, -1, -1):
            button = self.buttons[i]
            if not button.property(PERMANENT_PROPERTY):
                button.hide()
                button.deleteLater()
                del self.buttons[i]

    @DisableWidgetUpdatesContext.methodDecorator
    def setContext(self, locator: NavLocator, commitMessage: str = "", isStash=False):
        self.clearButtons()

        self.locator = locator

        if locator.context == NavContext.COMMITTED:
            kind = self.tr("Stash") if isStash else self.tr("Commit")
            summary, _ = messageSummary(commitMessage)
            self.mainLabel.setText(f"{kind} {shortHash(locator.commit)} – {summary}")

            infoButton = self.addButton(self.tr("Info"), lambda: GetCommitInfo.invoke(self, self.locator.commit))
            infoButton.setToolTip(self.tr("Show details about this commit") if not isStash
                                  else self.tr("Show details about this stash"))

            if isStash:
                dropButton = self.addButton(self.tr("Drop"), lambda: DropStash.invoke(self, locator.commit))
                dropButton.setToolTip(self.tr("Delete this stash"))

                applyButton = self.addButton(self.tr("Apply"), lambda: ApplyStash.invoke(self, locator.commit))
                applyButton.setToolTip(self.tr("Apply this stash"))

        elif locator.context.isWorkdir():
            self.mainLabel.setText(self.tr("Uncommitted changes"))
        else:
            # Special context (e.g. history truncated)
            self.mainLabel.setText(" ")
