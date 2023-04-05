from gitfourchette import settings
from gitfourchette.qt import *


class AutoHideMenuBar(QObject):
    def __init__(self, menuBar: QMenuBar):
        super().__init__(menuBar)

        self.setObjectName("AutoHideMenuBar")

        self.menuBar = menuBar
        self.defaultMaximumHeight = self.menuBar.maximumHeight()
        self.sticky = True

        menu: QMenu
        for menu in menuBar.findChildren(QMenu):
            menu.aboutToShow.connect(self.onMenuAboutToShow)
            menu.aboutToHide.connect(self.onMenuAboutToHide)

        self.refreshPrefs()

    def refreshPrefs(self):
        self.showMenuBar(not self.enabled)

    @property
    def enabled(self):
        return settings.prefs.autoHideMenuBar

    @property
    def isHidden(self):
        return self.menuBar.maximumHeight() == 0

    def showMenuBar(self, show):
        if show:
            self.menuBar.setMaximumHeight(self.defaultMaximumHeight)
        else:
            self.menuBar.setMaximumHeight(0)

    def toggle(self):
        if self.enabled:
            self.sticky = True
            self.showMenuBar(self.isHidden)

    def onMenuAboutToShow(self):
        if self.enabled and self.isHidden:
            self.showMenuBar(True)
            self.sticky = False

    def onMenuAboutToHide(self):
        if self.enabled and not self.isHidden and not self.sticky:
            self.showMenuBar(False)
