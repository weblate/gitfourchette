from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar, Callable

from gitfourchette.qt import *
from gitfourchette.toolbox.qtutils import stockIcon, MultiShortcut, appendShortcutToToolTipText


@dataclass
class ActionDef:
    """
    Build QMenus quickly with a list of ActionDefs.
    """

    SEPARATOR: ClassVar[None] = None

    caption: str = ""
    callback: Signal | Callable | None = None
    icon: str | QStyle.StandardPixmap = ""
    checkState: int = 0
    enabled: bool = True
    submenu: list[ActionDef] = field(default_factory=list)
    shortcuts: MultiShortcut | str = field(default_factory=list)
    statusTip: str = ""
    toolTip: str = ""
    objectName: str = ""
    menuRole: QAction.MenuRole = QAction.MenuRole.NoRole
    isSection: bool = False

    def toQAction(self, parent: QMenu) -> QAction:
        if self.submenu:
            raise NotImplementedError("ActionDef.toQAction cannot be used for submenus")

        action = QAction(self.caption, parent=parent)

        if self.objectName:
            action.setObjectName(self.objectName)

        if self.callback is None:
            pass
        elif type(self.callback) is SignalInstance:
            action.triggered.connect(self.callback)
        else:
            action.triggered.connect(lambda: self.callback())

        if self.icon:
            action.setIcon(stockIcon(self.icon))

        if self.checkState != 0:
            action.setCheckable(True)
            action.setChecked(self.checkState == 1)

        if self.statusTip:
            action.setStatusTip(self.statusTip)

        if self.toolTip:
            tip = self.toolTip
            if self.shortcuts:
                if type(self.shortcuts) is list:
                    tip = appendShortcutToToolTipText(tip, self.shortcuts[0])
                else:
                    tip = appendShortcutToToolTipText(tip, self.shortcuts)
            action.setToolTip(tip)

        if self.menuRole != QAction.MenuRole.NoRole:
            action.setMenuRole(self.menuRole)

        action.setEnabled(bool(self.enabled))

        if self.shortcuts:
            if type(self.shortcuts) is list:
                action.setShortcuts(self.shortcuts)
            else:
                action.setShortcut(self.shortcuts)

        return action

    def makeSubmenu(self, parent: QMenu) -> QMenu | None:
        if not self.submenu:
            return None

        submenu = ActionDef.makeQMenu(parent=parent, actionDefs=self.submenu)
        submenu.setTitle(self.caption)
        if self.icon:
            submenu.setIcon(stockIcon(self.icon))
        if self.objectName:
            submenu.setObjectName(self.objectName)

        return submenu

    @staticmethod
    def addToQMenu(menu: QMenu, *actionDefs: ActionDef | QAction):
        for actionDef in actionDefs:
            if not actionDef:
                menu.addSeparator()
            elif type(actionDef) is QAction:
                actionDef.setParent(menu)  # reparent it
                menu.addAction(actionDef)
            elif actionDef.isSection:
                menu.addSection(actionDef.caption)
            elif actionDef.submenu:
                submenu = actionDef.makeSubmenu(parent=menu)
                menu.addMenu(submenu)
            else:
                action = actionDef.toQAction(parent=menu)
                menu.addAction(action)

    @staticmethod
    def addToQToolBar(toolbar: QToolBar, *actionDefs: ActionDef | QAction):
        for item in actionDefs:
            if not item:
                toolbar.addSeparator()
            elif type(item) is QAction:
                action: QAction = item
                action.setParent(toolbar)  # reparent it
                action.setShortcut("")  # clear shortcut for toolbar
                toolbar.addAction(action)
            elif item.submenu:
                raise NotImplementedError("Cannot add ActionDef submenus to QToolbar")
            else:
                action = item.toQAction(parent=toolbar)
                action.setShortcut("")
                toolbar.addAction(action)

    @staticmethod
    def makeQMenu(
            parent: QWidget,
            actionDefs: list[ActionDef | QAction],
            bottomEntries: QMenu | None = None
    ) -> QMenu:

        menu = QMenu(parent)
        menu.setObjectName("ActionDefMenu")

        ActionDef.addToQMenu(menu, *actionDefs)

        if bottomEntries:
            menu.addSeparator()
            menu.addActions(bottomEntries.actions())

        return menu
