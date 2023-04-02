from dataclasses import dataclass, field
from gitfourchette.qt import *
from gitfourchette.toolbox.qtutils import stockIcon
import typing


@dataclass
class ActionDef:
    """
    Build QMenus quickly with a list of ActionDefs.
    """

    SEPARATOR: typing.ClassVar[None] = None

    caption: str = ""
    callback: Signal | typing.Callable | None = None
    icon: str | QStyle.StandardPixmap = ""
    checkState: int = 0
    enabled: bool = True
    submenu: list['ActionDef'] = field(default_factory=list)
    shortcuts: QKeySequence | list[QKeySequence] = field(default_factory=list)

    def toQAction(self, parent: QMenu) -> QAction:
        if self.submenu:
            raise NotImplementedError("ActionDef.toQAction cannot be used for submenus")

        action = QAction(self.caption, parent=parent)
        action.triggered.connect(self.callback)

        if self.icon:
            action.setIcon(stockIcon(self.icon))

        if self.checkState != 0:
            action.setCheckable(True)
            action.setChecked(self.checkState == 1)

        action.setEnabled(bool(self.enabled))

        if self.shortcuts:
            action.setShortcuts(self.shortcuts)

        return action

    def makeSubmenu(self, parent: QMenu) -> QMenu | None:
        if not self.submenu:
            return None

        submenu = ActionDef.makeQMenu(parent=parent, actionDefs=self.submenu)
        submenu.setTitle(self.caption)
        if self.icon:
            submenu.setIcon(stockIcon(self.icon))

        return submenu

    @staticmethod
    def addToQMenu(menu: QMenu, actionDefs: list['ActionDef']):
        for actionDef in actionDefs:
            if not actionDef:
                menu.addSeparator()
            elif actionDef.submenu:
                submenu = actionDef.makeSubmenu(parent=menu)
                menu.addMenu(submenu)
            else:
                action = actionDef.toQAction(parent=menu)
                menu.addAction(action)

    @staticmethod
    def makeQMenu(
            parent: QWidget,
            actionDefs: list['ActionDef'],
            bottomEntries: QMenu | None = None
    ) -> QMenu:

        menu = QMenu(parent)
        menu.setObjectName("ActionDefMenu")

        ActionDef.addToQMenu(menu, actionDefs)

        if bottomEntries:
            menu.addSeparator()
            menu.addActions(bottomEntries.actions())

        return menu
