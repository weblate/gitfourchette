from contextlib import suppress

from gitfourchette.globalshortcuts import GlobalShortcuts
from gitfourchette.qt import *
from gitfourchette.toolbox import *
from gitfourchette import settings
from gitfourchette import tasks
from gitfourchette.nav import NavLocator
from gitfourchette.tasks import TaskBook
from gitfourchette.repowidget import RepoWidget


class MainToolBar(QToolBar):
    openDialog = Signal()
    reveal = Signal()
    pull = Signal()
    push = Signal()

    observed: RepoWidget | None

    backAction: QAction
    forwardAction: QAction
    recentAction: QAction

    def __init__(self, parent: QWidget):
        super().__init__(translate("General", "Show Toolbar"), parent)  # PYQT5 compat: Don't call self.tr here

        self.observed = None

        self.setObjectName("GFToolbar")
        self.setMovable(False)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.onCustomContextMenuRequested)

        self.visibilityChanged.connect(self.onVisibilityChanged)
        self.toolButtonStyleChanged.connect(self.onToolButtonStyleChanged)
        self.iconSizeChanged.connect(self.onIconSizeChanged)

        self.backAction = TaskBook.toolbarAction(self, tasks.JumpBack)
        self.forwardAction = TaskBook.toolbarAction(self, tasks.JumpForward)
        self.recentAction = ActionDef(self.tr("Open..."), self.openDialog, icon="folder-open-recent",
                  shortcuts=QKeySequence.StandardKey.Open,
                  toolTip=self.tr("Open a Git repo on your machine")).toQAction(self)

        defs = [
            self.backAction,
            self.forwardAction,
            None,

            TaskBook.toolbarAction(self, tasks.FetchRemote),
            TaskBook.toolbarAction(self, tasks.PullBranch),
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
            self.recentAction,
        ]

        ActionDef.addToQToolBar(self, *defs)

        self.recentAction.setIconVisibleInMenu(True)
        recentButton: QToolButton = self.widgetForAction(self.recentAction)
        assert type(recentButton) is QToolButton
        recentButton.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)

        self.setToolButtonStyle(settings.prefs.toolBarButtonStyle)
        self.setIconSize(QSize(settings.prefs.toolBarIconSize, settings.prefs.toolBarIconSize))

        self.updateNavButtons()

    def setToolButtonStyle(self, style: Qt.ToolButtonStyle):
        # Resolve style
        if style == Qt.ToolButtonStyle.ToolButtonFollowStyle:
            style = QApplication.style().styleHint(QStyle.StyleHint.SH_ToolButtonStyle)

        # Hide back/forward button text with ToolButtonTextBesideIcon
        if style == Qt.ToolButtonStyle.ToolButtonTextBesideIcon:
            self.backAction.setText("")
            self.forwardAction.setText("")
        else:
            self.backAction.setText(TaskBook.toolbarNames[tasks.JumpBack])
            self.forwardAction.setText(TaskBook.toolbarNames[tasks.JumpForward])

        super().setToolButtonStyle(style)

    def onCustomContextMenuRequested(self, localPoint: QPoint):
        globalPoint = self.mapToGlobal(localPoint)

        def textPositionAction(name, style):
            return ActionDef(name,
                             callback=lambda: self.setToolButtonStyle(style),
                             checkState=1 if self.toolButtonStyle() == style else -1,
                             radioGroup="TextPosition")

        def iconSizeAction(name, size):
            return ActionDef(name,
                             callback=lambda: self.setIconSize(QSize(size, size)),
                             checkState=1 if self.iconSize().width() == size else -1,
                             radioGroup="IconSize")

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

    def observeRepoWidget(self, rw: RepoWidget | None):
        if rw is self.observed:
            return

        if self.observed is not None:
            with suppress(RuntimeError, TypeError):
                self.observed.historyChanged.disconnect(self.updateNavButtons)

        self.observed = rw

        if rw is not None:
            rw.historyChanged.connect(self.updateNavButtons)

        self.updateNavButtons()

    def updateNavButtons(self):
        rw = self.observed
        if rw is None:
            self.backAction.setEnabled(False)
            self.forwardAction.setEnabled(False)
        else:
            self.backAction.setEnabled(rw.navHistory.canGoBack())
            self.forwardAction.setEnabled(rw.navHistory.canGoForward())
