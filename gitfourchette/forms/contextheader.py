from gitfourchette.nav import NavLocator, NavContext, NavFlags
from gitfourchette.qt import *
from gitfourchette.tasks import GetCommitInfo
from gitfourchette.toolbox import *


class ContextHeader(QFrame):
    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("ContextHeader")

        layout = QHBoxLayout(self)
        self.setMinimumHeight(24)

        mainLabel = QElidedLabel(self)
        maximizeButton = QToolButton(self)
        maximizeButton.setCheckable(True)

        infoButton = QToolButton(self)
        infoButton.setText(self.tr("Commit Info"))
        infoButton.clicked.connect(lambda: GetCommitInfo.invoke(self, self.locator.commit))

        maximizeButton.setText(self.tr("Maximize"))
        maximizeButton.setToolTip(self.tr("Maximize the diff area and hide the commit graph"))
        for b in (maximizeButton, infoButton):
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(mainLabel)
        layout.addWidget(infoButton)
        layout.addWidget(maximizeButton)

        self.mainLabel = mainLabel
        self.infoButton = infoButton
        self.maximizeButton = maximizeButton

        bg = mutedTextColorHex(self, .07)
        fg = mutedTextColorHex(self, .8)
        self.setStyleSheet(f"ContextHeader {{ background-color: {bg}; }}  ContextHeader QLabel {{ color: {fg}; }}")

    def setContext(self, locator: NavLocator, commitMessage: str = ""):
        self.locator = locator
        if locator.context == NavContext.COMMITTED:
            kind = self.tr("Commit")
            if locator.hasFlags(NavFlags.IsStash):
                kind = self.tr("Stash")
            summary, _ = messageSummary(commitMessage)
            self.mainLabel.setText(f"{kind} {shortHash(locator.commit)} – {summary}")
            self.infoButton.setVisible(True)
        elif locator.context.isWorkdir():
            self.mainLabel.setText(self.tr("Uncommitted changes"))
            self.infoButton.setVisible(False)
