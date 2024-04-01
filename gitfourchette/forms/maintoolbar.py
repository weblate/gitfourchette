from gitfourchette.globalshortcuts import GlobalShortcuts
from gitfourchette.qt import *
from gitfourchette.toolbox import *
from gitfourchette import tasks
from gitfourchette.tasks import TaskBook


RECENT_OBJECT_NAME = "RecentMenuPlaceholder"


class MainToolbar(QToolBar):
    openDialog = Signal()
    reveal = Signal()
    pull = Signal()
    push = Signal()

    def __init__(self, parent: QWidget):
        super().__init__(translate("General", "Show Toolbar"), parent)  # PYQT5 compat: Don't call self.tr here

        self.setObjectName("GFToolbar")
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.setIconSize(QSize(16, 16))
        self.setMovable(False)

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
