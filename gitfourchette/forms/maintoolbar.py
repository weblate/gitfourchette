from gitfourchette.globalshortcuts import GlobalShortcuts
from gitfourchette.qt import *
from gitfourchette.toolbox import *
from gitfourchette import settings
from gitfourchette import tasks
from gitfourchette.tasks import TaskBook


RECENT_OBJECT_NAME = "RecentMenuPlaceholder"


class MainToolBar(QToolBar):
    openDialog = Signal()
    reveal = Signal()
    pull = Signal()
    push = Signal()

    def __init__(self, parent: QWidget):
        super().__init__(translate("General", "Show Toolbar"), parent)  # PYQT5 compat: Don't call self.tr here

        self.setObjectName("GFToolbar")
        self.setMovable(False)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.onCustomContextMenuRequested)

        self.setToolButtonStyle(settings.prefs.toolBarButtonStyle)
        self.setIconSize(QSize(settings.prefs.toolBarIconSize, settings.prefs.toolBarIconSize))

        self.visibilityChanged.connect(self.onVisibilityChanged)
        self.toolButtonStyleChanged.connect(self.onToolButtonStyleChanged)
        self.iconSizeChanged.connect(self.onIconSizeChanged)

        defs = [
            TaskBook.toolbarAction(self, tasks.JumpBack),
            TaskBook.toolbarAction(self, tasks.JumpForward),
            None,

            TaskBook.toolbarAction(self, tasks.FetchRemote),
            # TODO --------- ActionDef(self.tr("Pull"), self.pull, icon="vcs-pull"),
            ActionDef(self.tr("Push"), self.push, icon="vcs-push",
                      toolTip=self.tr("Push local branch to remote"),
                      shortcuts=GlobalShortcuts.pushBranch),
            None,

            TaskBook.toolbarAction(self, tasks.NewBranchFromHead),
            TaskBook.toolbarAction(self, tasks.NewStash),
            None,

            ActionDef(self.tr("Reveal"), self.reveal, icon="go-parent-folder",
                      shortcuts=GlobalShortcuts.openRepoFolder,
                      toolTip=self.tr("Open repo folder in file manager")),

            ActionDef(self.tr("Open..."), self.openDialog, icon="folder-open-recent",
                      shortcuts=QKeySequence.StandardKey.Open,
                      toolTip=self.tr("Open a Git repo on your machine"),
                      objectName=RECENT_OBJECT_NAME),
        ]

        ActionDef.addToQToolBar(self, *defs)

        self.recentAction: QAction = self.findChild(QAction, RECENT_OBJECT_NAME)
        self.recentAction.setIconVisibleInMenu(True)
        recentButton: QToolButton = self.widgetForAction(self.recentAction)
        assert type(recentButton) is QToolButton
        recentButton.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)

    def onCustomContextMenuRequested(self, localPoint: QPoint):
        globalPoint = self.mapToGlobal(localPoint)

        def textPositionAction(name, style):
            return ActionDef(name,
                             callback=lambda: self.setToolButtonStyle(style),
                             checkState=1 if self.toolButtonStyle() == style else -1)

        def iconSizeAction(name, size):
            return ActionDef(name,
                             callback=lambda: self.setIconSize(QSize(size, size)),
                             checkState=1 if self.iconSize().width() == size else -1)

        menu = ActionDef.makeQMenu(self, [
            self.toggleViewAction(),

            None,

            ActionDef(
                self.tr("Text Position"),
                submenu=[
                    textPositionAction(self.tr("Icons Only"), Qt.ToolButtonStyle.ToolButtonIconOnly),
                    textPositionAction(self.tr("Text Only"), Qt.ToolButtonStyle.ToolButtonTextOnly),
                    textPositionAction(self.tr("Text Alongside Icons"), Qt.ToolButtonStyle.ToolButtonTextBesideIcon),
                    textPositionAction(self.tr("Text Under Icons"), Qt.ToolButtonStyle.ToolButtonTextUnderIcon),
                ]
            ),

            ActionDef(
                self.tr("Icon Size"),
                submenu=[
                    iconSizeAction(self.tr("Small"), 16),
                    iconSizeAction(self.tr("Medium"), 24),
                    iconSizeAction(self.tr("Large"), 32),
                ]
            ),
        ])

        menu.exec(globalPoint)

    def onVisibilityChanged(self, visible: bool):
        self.window().setUnifiedTitleAndToolBarOnMac(visible)
        if visible == settings.prefs.showToolBar:
            return
        settings.prefs.showToolBar = visible
        settings.prefs.setDirty()

    def onToolButtonStyleChanged(self, style: Qt.ToolButtonStyle):
        if style == settings.prefs.toolBarButtonStyle:
            return
        settings.prefs.toolBarButtonStyle = style
        settings.prefs.setDirty()

    def onIconSizeChanged(self, size: QSize):
        w = size.width()
        if w == settings.prefs.toolBarIconSize:
            return
        settings.prefs.toolBarIconSize = w
        settings.prefs.setDirty()
