import gc
import re
from typing import Literal, Type

import pygit2

from gitfourchette import log
from gitfourchette import porcelain
from gitfourchette import settings
from gitfourchette import tasks
from gitfourchette.diffview.diffview import DiffView
from gitfourchette.exttools import openInTextEditor
from gitfourchette.forms.aboutdialog import showAboutDialog
from gitfourchette.forms.clonedialog import CloneDialog
from gitfourchette.forms.prefsdialog import PrefsDialog
from gitfourchette.forms.welcomewidget import WelcomeWidget
from gitfourchette.globalshortcuts import GlobalShortcuts
from gitfourchette.porcelain import *
from gitfourchette.qt import *
from gitfourchette.repostate import RepoState
from gitfourchette.repowidget import RepoWidget
from gitfourchette.tasks import TaskInvoker, TaskBook, RepoTask
from gitfourchette.toolbox import *


class MainWindow(QMainWindow):
    styleSheetReloadScheduled = False

    welcomeStack: QStackedWidget
    welcomeWidget: WelcomeWidget
    tabs: QTabWidget2
    recentMenu: QMenu
    repoMenu: QMenu

    def __init__(self):
        super().__init__()

        # Initialize global shortcuts
        GlobalShortcuts.initialize()

        # Initialize task book
        TaskBook.initialize()
        TaskInvoker.instance().invokeSignal.connect(self.onInvokeTask)

        self.setObjectName("GFMainWindow")

        self.sharedSplitterStates = {}

        self.setWindowTitle(qAppName())
        self.resize(QSize(800, 600))
        self.move(QPoint(50, 50))

        self.tabs = QTabWidget2(self)
        self.tabs.currentWidgetChanged.connect(self.onTabCurrentWidgetChanged)
        self.tabs.tabCloseRequested.connect(self.closeTab)
        self.tabs.tabContextMenuRequested.connect(self.onTabContextMenu)
        self.tabs.tabDoubleClicked.connect(self.onTabDoubleClicked)

        self.welcomeWidget = WelcomeWidget(self)
        self.welcomeWidget.newRepo.connect(self.newRepo)
        self.welcomeWidget.openRepo.connect(self.openDialog)
        self.welcomeWidget.cloneRepo.connect(self.cloneDialog)

        self.welcomeStack = QStackedWidget()
        self.welcomeStack.addWidget(self.welcomeWidget)
        self.welcomeStack.addWidget(self.tabs)
        self.welcomeStack.setCurrentWidget(self.welcomeWidget)
        self.setCentralWidget(self.welcomeStack)

        self.globalMenuBar = QMenuBar(self)
        self.globalMenuBar.setObjectName("GFMainMenuBar")
        self.autoHideMenuBar = AutoHideMenuBar(self.globalMenuBar)
        self.fillGlobalMenuBar()
        self.setMenuBar(self.globalMenuBar)

        self.statusBar2 = QStatusBar2(self)
        self.setStatusBar(self.statusBar2)

        self.setAcceptDrops(True)
        self.styleSheetReloadScheduled = False
        QApplication.instance().installEventFilter(self)

        self.refreshPrefs()

    # -------------------------------------------------------------------------

    def close(self) -> bool:
        TaskInvoker.instance().invokeSignal.disconnect(self.onInvokeTask)
        return super().close()

    def onInvokeTask(self, taskType: Type[RepoTask], taskArgs: tuple):
        rw = self.currentRepoWidget()
        if rw:
            rw.runTask(taskType, *taskArgs)
        else:
            showInformation(self, TaskBook.names.get(taskType, taskType.name()),
                            self.tr("Please open a repository before performing this action."))

    # -------------------------------------------------------------------------

    @staticmethod
    def reloadStyleSheet():
        log.verbose("MainWindow", "Reloading QSS")
        with NonCriticalOperation("Reload application-wide stylesheet"):
            MainWindow.styleSheetReloadScheduled = False
            styleSheetFile = QFile("assets:style.qss")
            if not styleSheetFile.open(QFile.OpenModeFlag.ReadOnly):
                return
            styleSheet = styleSheetFile.readAll().data().decode("utf-8")
            QApplication.instance().setStyleSheet(styleSheet)
            styleSheetFile.close()
            clearStockIconCache()

    # -------------------------------------------------------------------------
    # Event filters & handlers

    def eventFilter(self, watched, event: QEvent):
        isPress = event.type() == QEvent.Type.MouseButtonPress
        isDblClick = event.type() == QEvent.Type.MouseButtonDblClick

        if event.type() == QEvent.Type.FileOpen:
            # Called if dragging something to dock icon on macOS.
            # Ignore in test mode - the test runner may send a bogus FileOpen before we're ready to process it.
            if not settings.TEST_MODE:
                outcome = self.getDropOutcomeFromLocalFilePath(event.file())
                self.handleDrop(*outcome)

        elif event.type() == QEvent.Type.ApplicationStateChange:
            # Refresh current RepoWidget when the app regains the active state (foreground)
            if QGuiApplication.applicationState() == Qt.ApplicationState.ApplicationActive:
                QTimer.singleShot(0, self.onRegainForeground)

        elif event.type() == QEvent.Type.ThemeChange:
            # Reload QSS when the theme changes (e.g. switching between dark/light modes).
            # Delay the reload to next event loop so that it doesn't occur during the fade animation on macOS.
            # We may receive several ThemeChange events during a single theme change, so only schedule one reload.
            if not MainWindow.styleSheetReloadScheduled:
                MainWindow.styleSheetReloadScheduled = True
                QTimer.singleShot(0, MainWindow.reloadStyleSheet)
                return True

        elif (isPress or isDblClick) and self.isActiveWindow():
            # As of PyQt6 6.5.1, QContextMenuEvent sometimes pretends that its event type is a MouseButtonDblClick
            if PYQT6 and not isinstance(event, QMouseEvent):
                return False

            mouseEvent: QMouseEvent = event

            isBack = mouseEvent.button() == Qt.MouseButton.BackButton
            isForward = mouseEvent.button() == Qt.MouseButton.ForwardButton

            if isBack or isForward:
                if isPress:
                    rw = self.currentRepoWidget()
                    if rw and isBack:
                        rw.navigateBack()
                    elif rw and isForward:
                        rw.navigateForward()

                # Eat clicks or double-clicks of back and forward mouse buttons
                return True

        return False

    def keyReleaseEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Alt and self.autoHideMenuBar.enabled:
            self.autoHideMenuBar.toggle()
        else:
            super().keyReleaseEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent):
        action, data = self.getDropOutcomeFromMimeData(event.mimeData())
        if action:
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        action, data = self.getDropOutcomeFromMimeData(event.mimeData())
        event.setAccepted(True)  # keep dragged item from coming back to cursor on macOS
        self.handleDrop(action, data)

    # -------------------------------------------------------------------------
    # Menu bar

    def fillGlobalMenuBar(self):
        menubar = self.globalMenuBar
        menubar.clear()

        # -------------------------------------------------------------

        fileMenu = menubar.addMenu(self.tr("&File"))
        fileMenu.setObjectName("MWFileMenu")

        ActionDef.addToQMenu(
            fileMenu,

            ActionDef(self.tr("&New Repository..."), self.newRepo,
                      shortcuts=QKeySequence.StandardKey.New, icon="folder-new",
                      statusTip=self.tr("Create an empty Git repo")),

            ActionDef(self.tr("C&lone Repository..."), self.cloneDialog,
                      shortcuts="Ctrl+Shift+N", icon="folder-download",
                      statusTip=self.tr("Download a Git repo and open it")),

            ActionDef.SEPARATOR,

            ActionDef(self.tr("&Open Repository..."), self.openDialog,
                      shortcuts=QKeySequence.StandardKey.Open, icon="folder-open",
                      statusTip=self.tr("Open a Git repo on your machine")),

            ActionDef(self.tr("Open &Recent"),
                      icon="folder-open-recent",
                      statusTip=self.tr("List of recently opened Git repos"),
                      objectName="RecentMenuPlaceholder"),

            ActionDef.SEPARATOR,

            TaskBook.action(tasks.NewCommit, "&C"),
            TaskBook.action(tasks.AmendCommit, "&A"),
            TaskBook.action(tasks.NewStash),

            ActionDef.SEPARATOR,

            TaskBook.action(tasks.ApplyPatchFile),
            TaskBook.action(tasks.ApplyPatchFileReverse),

            ActionDef.SEPARATOR,

            ActionDef(self.tr("&Preferences..."), self.openPrefsDialog,
                      shortcuts=QKeySequence.StandardKey.Preferences, icon="configure",
                      menuRole=QAction.MenuRole.PreferencesRole,
                      statusTip=self.tr("Edit {app} settings").format(app=qAppName())),

            TaskBook.action(tasks.SetUpRepoIdentity, menuRole=QAction.MenuRole.ApplicationSpecificRole),

            ActionDef.SEPARATOR,

            ActionDef(self.tr("&Close Tab"), self.dispatchCloseCommand,
                      shortcuts=QKeySequence.StandardKey.Close, icon="document-close",
                      statusTip=self.tr("Close current repository tab")),

            ActionDef(self.tr("&Quit"), self.close,
                      shortcuts=QKeySequence.StandardKey.Quit, icon="application-exit",
                      statusTip=self.tr("Quit {app}").format(app=qAppName()),
                      menuRole=QAction.MenuRole.QuitRole),
        )

        # -------------------------------------------------------------

        editMenu: QMenu = menubar.addMenu(self.tr("&Edit"))
        editMenu.setObjectName("MWEditMenu")

        ActionDef.addToQMenu(
            editMenu,

            ActionDef(self.tr("&Find..."), lambda: self.dispatchSearchCommand("start"),
                      shortcuts=QKeySequence.StandardKey.Find, icon="edit-find",
                      statusTip=self.tr("Search for a piece of text in commit messages or in the current diff")),

            ActionDef(self.tr("Find Next"), lambda: self.dispatchSearchCommand("next"),
                      shortcuts=QKeySequence.StandardKey.FindNext,
                      statusTip=self.tr("Find next occurrence")),

            ActionDef(self.tr("Find Previous"), lambda: self.dispatchSearchCommand("previous"),
                      shortcuts=QKeySequence.StandardKey.FindPrevious,
                      statusTip=self.tr("Find previous occurrence"))
        )

        # -------------------------------------------------------------

        repoMenu: QMenu = menubar.addMenu(self.tr("&Repo"))
        repoMenu.setObjectName("MWRepoMenu")
        # repoMenu.setEnabled(False)
        self.repoMenu = repoMenu

        repoMenu.addSeparator()

        a = repoMenu.addAction(self.tr("Add Re&mote..."))
        TaskBook.fillAction(a, tasks.NewRemote)

        repoMenu.addSeparator()

        configFilesMenu = repoMenu.addMenu(self.tr("&Local Config Files"))

        a = repoMenu.addAction(self.tr("&Open Repo Folder"), self.openRepoFolder)
        a.setShortcuts(GlobalShortcuts.openRepoFolder)
        a.setStatusTip(self.tr("Open this repo’s working directory in the system’s file manager"))

        a = repoMenu.addAction(self.tr("Cop&y Repo Path"), self.copyRepoPath)
        a.setStatusTip(self.tr("Copy the absolute path to this repo’s working directory to the clipboard"))

        a = repoMenu.addAction(self.tr("Rename Repo..."), self.renameRepo)
        a.setStatusTip(self.tr("Give this repo a nickname (within {app} only)").format(app=qAppName()))

        repoMenu.addSeparator()

        a = repoMenu.addAction(self.tr("Open Trash..."), self.openRescueFolder)
        a.setIcon(stockIcon(QStyle.StandardPixmap.SP_TrashIcon))
        a.setStatusTip(self.tr("Explore changes that you may have discarded by mistake"))

        a = repoMenu.addAction(self.tr("Empty Trash..."), self.clearRescueFolder)
        a.setStatusTip(self.tr("Delete all discarded changes from the trash folder"))

        a = repoMenu.addAction(self.tr("Recall Lost Commit..."))
        TaskBook.fillAction(a, tasks.RecallCommit)

        repoMenu.addSeparator()

        a = repoMenu.addAction(self.tr("&Refresh"), self.refreshRepo)
        a.setShortcuts(GlobalShortcuts.refresh)
        a.setIcon(stockIcon(QStyle.StandardPixmap.SP_BrowserReload))
        a.setStatusTip(self.tr("Check for changes in the repo on the local filesystem only"))

        a = repoMenu.addAction(self.tr("Reloa&d"), self.hardRefresh)
        a.setShortcut("Ctrl+F5")
        a.setStatusTip(self.tr("Reopen the repo from scratch"))

        configFilesMenu.addAction(".gitignore", self.openGitignore)
        configFilesMenu.addAction("config", self.openLocalConfig)
        configFilesMenu.addAction("exclude", self.openLocalExclude)

        # -------------------------------------------------------------

        branchMenu = menubar.addMenu(self.tr("&Branch"))
        branchMenu.setObjectName("MWBranchMenu")

        ActionDef.addToQMenu(
            branchMenu,

            TaskBook.action(tasks.NewBranchFromHead, "&B"),

            ActionDef.SEPARATOR,

            ActionDef(
                self.tr("&Push Branch..."),
                self.pushBranch,
                "vcs-push",
                shortcuts=GlobalShortcuts.pushBranch,
                statusTip=self.tr("Upload your commits on the current branch to the remote server"),
            ),

            ActionDef.SEPARATOR,

            TaskBook.action(tasks.FetchRemoteBranch, "&F"),

            TaskBook.action(tasks.FastForwardBranch, "&d"),
        )

        # -------------------------------------------------------------

        goMenu: QMenu = menubar.addMenu(self.tr("&Go"))
        goMenu.setObjectName("MWGoMenu")

        ActionDef.addToQMenu(
            goMenu,
            ActionDef(self.tr("&Uncommitted Changes"), self.selectUncommittedChanges, shortcuts="Ctrl+U"),
            ActionDef.SEPARATOR,
            ActionDef(self.tr("&Next Tab"), self.nextTab, shortcuts="Ctrl+Tab"),
            ActionDef(self.tr("&Previous Tab"), self.previousTab, shortcuts="Ctrl+Shift+Tab"),
            ActionDef.SEPARATOR,
            ActionDef(self.tr("Next File"), self.nextFile, shortcuts="Ctrl+]"),
            ActionDef(self.tr("Previous File"), self.previousFile, shortcuts="Ctrl+["),
            ActionDef.SEPARATOR,
            TaskBook.action(tasks.JumpBack),
            TaskBook.action(tasks.JumpForward),
        )

        if DEVDEBUG:
            a = goMenu.addAction(self.tr("Navigation Log"), lambda: print(self.currentRepoWidget().navHistory.getTextLog()))
            a.setShortcut("Alt+Down")

        # -------------------------------------------------------------

        helpMenu = menubar.addMenu(self.tr("&Help"))
        helpMenu.setObjectName("MWHelpMenu")

        a = helpMenu.addAction(self.tr("&About {0}").format(qAppName()), lambda: showAboutDialog(self))
        a.setMenuRole(QAction.MenuRole.AboutRole)
        a.setIcon(QIcon("assets:gitfourchette-simple.png"))

        # -------------------------------------------------------------

        recentAction = fileMenu.findChild(QAction, "RecentMenuPlaceholder")
        self.recentMenu = QMenu(fileMenu)
        recentAction.setMenu(self.recentMenu)
        self.recentMenu.setObjectName("RecentMenu")
        self.fillRecentMenu()

    def fillRecentMenu(self):
        def onClearRecents():
            settings.history.clearRepoHistory()
            settings.history.write()
            self.fillRecentMenu()

        self.recentMenu.clear()
        for path in settings.history.getRecentRepoPaths(settings.prefs.maxRecentRepos):
            shortName = settings.history.getRepoTabName(path)
            action = self.recentMenu.addAction(shortName, lambda p=path: self.openRepo(p, exactMatch=True))
            action.setStatusTip(path)
        self.recentMenu.addSeparator()

        clearAction = self.recentMenu.addAction(self.tr("Clear List", "clear list of recently opened repositories"), onClearRecents)
        clearAction.setStatusTip(self.tr("Clear the list of recently opened repositories"))
        clearAction.setIcon(stockIcon("edit-clear-history"))

        self.welcomeWidget.ui.recentReposButton.setMenu(self.recentMenu)

    # -------------------------------------------------------------------------
    # Tabs

    def currentRepoWidget(self) -> RepoWidget:
        return self.tabs.currentWidget()

    def onTabCurrentWidgetChanged(self):
        w = self.currentRepoWidget()

        if not w:
            return

        # Get out of welcome widget
        self.welcomeStack.setCurrentWidget(self.tabs)

        w.refreshWindowTitle()  # Refresh window title before loading
        w.restoreSplitterStates()

        # If we don't have a RepoState, then the tab is lazy-loaded.
        # We need to load it now.
        if not w.isLoaded:
            w.primeRepo()
        else:
            # Trigger repo refresh.
            w.onRegainForeground()
            w.refreshWindowTitle()

    def generateTabContextMenu(self, i: int):
        if i < 0:  # Right mouse button released outside tabs
            return None

        rw: RepoWidget = self.tabs.widget(i)
        menu = QMenu(self)
        menu.setObjectName("MWRepoTabContextMenu")

        superproject = rw.state.superproject if rw.state else settings.history.getRepoSuperproject(rw.workdir)
        if superproject:
            superprojectName = escamp(settings.history.getRepoTabName(superproject))
            superprojectLabel = self.tr("Open Superproject “{0}”").format(superprojectName)
        else:
            superprojectLabel = self.tr("Open Superproject")

        ActionDef.addToQMenu(
            menu,
            ActionDef(self.tr("Close Tab"), lambda: self.closeTab(i), shortcuts=QKeySequence.StandardKey.Close),
            ActionDef(self.tr("Close Other Tabs"), lambda: self.closeOtherTabs(i)),
            ActionDef.SEPARATOR,
            ActionDef(self.tr("Open Repo Folder"), lambda: self.openRepoFolder(rw), shortcuts=GlobalShortcuts.openRepoFolder),
            ActionDef(self.tr("Copy Repo Path"), lambda: self.copyRepoPath(rw)),
            ActionDef(self.tr("Rename", "RepoTabCM"), lambda: self.renameRepo(rw)),
            ActionDef.SEPARATOR,
            ActionDef(superprojectLabel, lambda: self.openRepoNextTo(rw, superproject), enabled=bool(superproject)),
            ActionDef.SEPARATOR
        )

        if rw.state:
            ActionDef.addToQMenu(menu, ActionDef(self.tr("Unload", "RepoTabCM"), lambda: self.unloadTab(i)))
        else:
            ActionDef.addToQMenu(menu, ActionDef(self.tr("Load", "RepoTabCM"), lambda: self.loadTab(i)))

        return menu

    def onTabContextMenu(self, globalPoint: QPoint, i: int):
        if i < 0:  # Right mouse button released outside tabs
            return

        menu = self.generateTabContextMenu(i)
        menu.exec(globalPoint)
        menu.deleteLater()

    def onTabDoubleClicked(self, i: int):
        if i < 0:
            return
        rw: RepoWidget = self.tabs.widget(i)
        if settings.prefs.tabs_doubleClickOpensFolder:
            self.openRepoFolder(rw)

    # -------------------------------------------------------------------------
    # Repo loading

    def openRepo(self, path: str, exactMatch=True) -> RepoWidget | None:
        try:
            rw = self._openRepo(path, exactMatch=exactMatch)
        except BaseException as exc:
            excMessageBox(
                exc,
                self.tr("Open repository"),
                self.tr("Couldn’t open the repository at “{0}”.").format(escape(path)),
                parent=self,
                icon='warning')
            return None

        self.saveSession()
        return rw

    def _openRepo(self, path: str, foreground=True, tabIndex=-1, exactMatch=True) -> RepoWidget:
        # Make sure the path exists
        if not os.path.exists(path):
            raise FileNotFoundError(self.tr("There’s nothing at this path."))

        # Get the workdir
        if exactMatch:
            workdir = path
        else:
            with RepoContext(path) as repo:
                workdir = repo.workdir

        # First check that we don't have a tab for this repo already
        for i in range(self.tabs.count()):
            existingRW: RepoWidget = self.tabs.widget(i)
            if os.path.samefile(workdir, existingRW.workdir):
                self.tabs.setCurrentIndex(i)
                return existingRW

        # Create a RepoWidget
        rw = RepoWidget(self)
        rw.setPendingWorkdir(workdir)

        # Hook RepoWidget signals
        rw.setSharedSplitterState(self.sharedSplitterStates)

        rw.nameChange.connect(lambda: self.refreshTabText(rw))
        rw.nameChange.connect(lambda: rw.refreshWindowTitle())
        rw.openRepo.connect(lambda path: self.openRepoNextTo(rw, path))
        rw.openPrefs.connect(self.openPrefsDialog)

        rw.statusMessage.connect(self.statusBar2.showMessage)
        rw.busyMessage.connect(self.statusBar2.showBusyMessage)
        rw.clearStatus.connect(self.statusBar2.clearMessage)
        rw.statusWarning.connect(self.statusBar2.showPermanentWarning)

        # Create a tab for the RepoWidget
        with QSignalBlockerContext(self.tabs):
            tabIndex = self.tabs.insertTab(tabIndex, rw, rw.getTitle())
            self.tabs.setTabTooltip(tabIndex, compactPath(workdir))
            if foreground:
                self.tabs.setCurrentIndex(tabIndex)

        # Switch away from WelcomeWidget
        self.welcomeStack.setCurrentWidget(self.tabs)

        # Load repo now
        if foreground:
            rw.primeRepo()

        return rw

    # -------------------------------------------------------------------------

    def onRegainForeground(self):
        rw = self.currentRepoWidget()
        if not rw:
            return
        if QGuiApplication.applicationState() != Qt.ApplicationState.ApplicationActive:
            return
        if not settings.prefs.debug_autoRefresh:
            return
        rw.onRegainForeground()

    # -------------------------------------------------------------------------
    # Repo menu callbacks

    @staticmethod
    def needRepoWidget(callback):
        def wrapper(self, rw=None):
            if rw is None:
                rw = self.currentRepoWidget()
            if rw:
                callback(self, rw)
            else:
                showInformation(self, self.tr("No repository"),
                                self.tr("Please open a repository before performing this action."))
        return wrapper

    @needRepoWidget
    def refreshRepo(self, rw: RepoWidget):
        rw.refreshRepo()

    @needRepoWidget
    def hardRefresh(self, rw: RepoWidget):
        rw.primeRepo(force=True)

    @needRepoWidget
    def openRepoFolder(self, rw: RepoWidget):
        openFolder(rw.workdir)

    @needRepoWidget
    def copyRepoPath(self, rw: RepoWidget):
        QApplication.clipboard().setText(rw.workdir)

    @needRepoWidget
    def renameRepo(self, rw: RepoWidget):
        rw.renameRepo()

    @needRepoWidget
    def pushBranch(self, rw: RepoWidget):
        rw.startPushFlow()

    @needRepoWidget
    def openRescueFolder(self, rw: RepoWidget):
        rw.openRescueFolder()

    @needRepoWidget
    def clearRescueFolder(self, rw: RepoWidget):
        rw.clearRescueFolder()

    def _openLocalConfigFile(self, fullPath: str):
        def createAndOpen():
            open(fullPath, "ab").close()
            openInTextEditor(self, fullPath)

        if not os.path.exists(fullPath):
            basename = os.path.basename(fullPath)
            askConfirmation(
                self,
                self.tr("Open “{0}”").format(basename),
                paragraphs(
                    self.tr("There’s no file at this location:") + "<br>" + escape(fullPath),
                    self.tr("Do you want to create it?")),
                okButtonText=self.tr("Create “{0}”").format(basename),
                callback=createAndOpen)
        else:
            openInTextEditor(self, fullPath)

    @needRepoWidget
    def openGitignore(self, rw: RepoWidget):
        self._openLocalConfigFile(os.path.join(rw.repo.workdir, ".gitignore"))

    @needRepoWidget
    def openLocalConfig(self, rw: RepoWidget):
        self._openLocalConfigFile(os.path.join(rw.repo.path, "config"))

    @needRepoWidget
    def openLocalExclude(self, rw: RepoWidget):
        self._openLocalConfigFile(os.path.join(rw.repo.path, "info", "exclude"))

    # -------------------------------------------------------------------------
    # Go menu

    @needRepoWidget
    def selectUncommittedChanges(self, rw: RepoWidget):
        rw.graphView.selectUncommittedChanges()

    @needRepoWidget
    def nextFile(self, rw: RepoWidget):
        rw.selectNextFile(True)

    @needRepoWidget
    def previousFile(self, rw: RepoWidget):
        rw.selectNextFile(False)

    # -------------------------------------------------------------------------
    # File menu callbacks

    def newRepo(self, path="", detectParentRepo=True):
        if not path:
            qfd = PersistentFileDialog.saveDirectory(self, "NewRepo", self.tr("New repository"))
            qfd.setLabelText(QFileDialog.DialogLabel.Accept, self.tr("&Create repo in this folder"))
            qfd.fileSelected.connect(self.newRepo)
            qfd.show()
            return

        parentRepo: str = ""
        if detectParentRepo:
            parentRepo = pygit2.discover_repository(path)

        if not detectParentRepo or not parentRepo:
            try:
                pygit2.init_repository(path)
                self.openRepo(path, exactMatch=True)
            except BaseException as exc:
                message = self.tr("Couldn’t create an empty repository in “{0}”.").format(escape(path))
                excMessageBox(exc, self.tr("New repository"), message, parent=self, icon='warning')

        if parentRepo:
            parentRepo = os.path.normpath(parentRepo)
            parentWorkdir = os.path.dirname(parentRepo) if os.path.basename(parentRepo) == ".git" else parentRepo

            if parentRepo == path or parentWorkdir == path:
                message = paragraphs(
                    self.tr("A repository already exists here:"),
                    "\t" + escape(parentWorkdir))
                qmb = asyncMessageBox(
                    self, 'information', self.tr("Repository already exists"), message,
                    QMessageBox.StandardButton.Open | QMessageBox.StandardButton.Cancel)
                qmb.button(QMessageBox.StandardButton.Open).setText(self.tr("&Open existing repo"))
                qmb.accepted.connect(lambda: self.openRepo(parentWorkdir, exactMatch=True))
                qmb.show()
            else:
                message = paragraphs(
                    self.tr("You want to create a repository in:"),
                    "\t" + escape(path),
                    self.tr("A repository already exists in a parent folder:"),
                    "\t" + escape(parentWorkdir),
                    self.tr("Do you want to create a new repository in the subfolder anyway?")
                )
                qmb = asyncMessageBox(
                    self, 'information', self.tr("Repository found in parent folder"), message,
                    QMessageBox.StandardButton.Open | QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
                openButton = qmb.button(QMessageBox.StandardButton.Open)
                openButton.setText(self.tr("&Open parent repo “{0}”").format(os.path.basename(parentWorkdir)))
                openButton.clicked.connect(lambda: self.openRepo(parentWorkdir, exactMatch=True))
                createButton = qmb.button(QMessageBox.StandardButton.Ok)
                createButton.setText(self.tr("&Create repo in subfolder"))
                createButton.clicked.connect(lambda: self.newRepo(path, detectParentRepo=False))
                qmb.show()
            return

    def cloneDialog(self, initialUrl: str = ""):
        dlg = CloneDialog(initialUrl, self)

        dlg.cloneSuccessful.connect(lambda path: self.openRepo(path))

        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        setWindowModal(dlg)
        dlg.show()

    def openDialog(self):
        qfd = PersistentFileDialog.openDirectory(self, "NewRepo", self.tr("Open repository"))
        qfd.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)  # don't leak dialog
        qfd.fileSelected.connect(lambda path: self.openRepo(path, exactMatch=False))
        qfd.show()

    # -------------------------------------------------------------------------
    # Tab management

    def dispatchCloseCommand(self):
        if self.isActiveWindow():
            self.closeCurrentTab()
        elif isinstance(QApplication.activeWindow(), DiffView):
            QApplication.activeWindow().close()

    def closeCurrentTab(self):
        if self.tabs.count() == 0:  # don't attempt to close if no tabs are open
            QApplication.beep()
            return

        self.closeTab(self.tabs.currentIndex())

    def closeTab(self, index: int, singleTab: bool = True):
        widget = self.tabs.widget(index)
        widget.close()  # will call RepoWidget.cleanup
        self.tabs.removeTab(index)
        widget.deleteLater()

        # If that was the last tab, back to welcome widget
        if self.tabs.count() == 0:
            self.welcomeStack.setCurrentWidget(self.welcomeWidget)
            self.setWindowTitle(qAppName())

        if singleTab:
            self.saveSession()
            gc.collect()

    def closeOtherTabs(self, index: int):
        # First, set this tab as active so an active tab that gets closed doesn't trigger other tabs to load.
        self.tabs.setCurrentIndex(index)

        # Now close all tabs in reverse order but skip the index we want to keep.
        start = self.tabs.count()-1
        for i in range(start, -1, -1):
            if i != index:
                self.closeTab(i, False)

        self.saveSession()
        gc.collect()

    def closeAllTabs(self):
        start = self.tabs.count() - 1
        with QSignalBlockerContext(self.tabs):  # Don't let awaken unloaded tabs
            for i in range(start, -1, -1):  # Close tabs in reverse order
                self.closeTab(i, False)

    def refreshTabText(self, rw):
        index = self.tabs.indexOf(rw)
        self.tabs.tabs.setTabText(index, rw.getTitle())

    def unloadTab(self, index: int):
        rw : RepoWidget = self.tabs.widget(index)
        rw.cleanup()
        gc.collect()
        self.refreshTabText(rw)

    def loadTab(self, index: int):
        rw : RepoWidget = self.tabs.widget(index)
        rw.primeRepo()

    def openRepoNextTo(self, rw, path: str):
        index = self.tabs.indexOf(rw)
        if index >= 0:
            index += 1
        return self._openRepo(path, tabIndex=index, exactMatch=True)

    def nextTab(self):
        if self.tabs.count() == 0:
            QApplication.beep()
            return
        index = self.tabs.currentIndex()
        index += 1
        index %= self.tabs.count()
        self.tabs.setCurrentIndex(index)

    def previousTab(self):
        if self.tabs.count() == 0:
            QApplication.beep()
            return
        index = self.tabs.currentIndex()
        index += self.tabs.count() - 1
        index %= self.tabs.count()
        self.tabs.setCurrentIndex(index)

    # -------------------------------------------------------------------------
    # Session management

    def restoreSession(self, session: settings.Session):
        self.sharedSplitterStates = {k: session.splitterStates[k] for k in session.splitterStates}
        self.restoreGeometry(session.windowGeometry)

        # Stop here if there are no tabs to load
        if not session.tabs:
            return

        errors = []

        # Normally, changing the current tab will load the corresponding repo in the background.
        # But we don't want to load every repo as we're creating tabs, so temporarily disconnect the signal.
        with QSignalBlockerContext(self.tabs):
            # We might not be able to load all tabs, so we may have to adjust session.activeTabIndex.
            activeTab = -1
            successfulRepos = []

            # Lazy-loading: prepare all tabs, but don't load the repos (foreground=False).
            for i, path in enumerate(session.tabs):
                try:
                    newRepoWidget = self._openRepo(path, foreground=False)
                except (GitError, OSError, NotImplementedError) as exc:
                    # GitError: most errors thrown by pygit2
                    # OSError: e.g. permission denied
                    # NotImplementedError: e.g. shallow/bare repos
                    errors.append((path, exc))
                    continue

                # _openRepo may still return None without throwing an exception in case of failure
                if newRepoWidget is None:
                    continue

                successfulRepos.append(path)

                if i == session.activeTabIndex:
                    activeTab = self.tabs.count()-1

            # If we failed to load anything, tell the user about it
            if errors:
                self._reportSessionErrors(errors)

            # Update history (don't write it yet - onTabCurrentWidgetChanged will do it below)
            for path in reversed(successfulRepos):
                settings.history.addRepo(path)
            self.fillRecentMenu()

            # Fall back to tab #0 if the previously active tab couldn't be restored
            # (Otherwise welcome page will stick around)
            if activeTab < 0 and len(successfulRepos):
                activeTab = 0

            # Set current tab and load its repo.
            if activeTab >= 0:
                self.tabs.setCurrentIndex(session.activeTabIndex)
                self.onTabCurrentWidgetChanged()

    def _reportSessionErrors(self, errors: list[tuple[str, BaseException]]):
        numErrors = len(errors)
        text = self.tr("The session couldn’t be restored fully because %n repositories failed to load:", "", numErrors)

        for path, exc in errors:
            errorText = str(exc)

            # Translate some common GitError texts
            if errorText.startswith("Repository not found at "):
                errorText = self.tr("Repository not found at this path.")

            text += F"<small><br><br></small>{escape(path)}<small><br>{errorText}</small>"

        showWarning(self, self.tr("Restore session"), text)

    def saveSession(self):
        session = settings.Session()
        session.windowGeometry = bytes(self.saveGeometry())
        if self.currentRepoWidget():
            session.splitterStates = {s.objectName(): bytes(s.saveState()) for s in self.currentRepoWidget().splittersToSave}
        else:
            session.splitterStates = {}
        session.tabs = [self.tabs.widget(i).workdir for i in range(self.tabs.count())]
        session.activeTabIndex = self.tabs.currentIndex()
        session.write()

    def closeEvent(self, e):
        QApplication.instance().removeEventFilter(self)

        # Save session before closing all tabs.
        self.saveSession()

        # Close all tabs so RepoWidgets release all their resources.
        # Important so unit tests wind down properly!
        self.closeAllTabs()

        e.accept()

    # -------------------------------------------------------------------------
    # Drag and drop

    @staticmethod
    def getDropOutcomeFromLocalFilePath(path: str) -> tuple[Literal["", "patch", "open"], str]:
        if path.endswith(".patch"):
            return "patch", path
        else:
            return "open", path

    @staticmethod
    def getDropOutcomeFromMimeData(mime: QMimeData) -> tuple[Literal["", "patch", "open", "clone"], str]:
        if mime.hasUrls() and len(mime.urls()) > 0:
            url: QUrl = mime.urls()[0]
            if url.isLocalFile():
                path = url.toLocalFile()
                return MainWindow.getDropOutcomeFromLocalFilePath(path)
            else:
                return "clone", url.toString()

        elif mime.hasText():
            text = mime.text()
            if os.path.isabs(text) and os.path.exists(text):
                return "open", text
            elif text.startswith(("ssh://", "git+ssh://", "https://", "http://")):
                return "clone", text
            elif re.match(r"^[a-zA-Z0-9-_.]+@.+:.+", text):
                return "clone", text
            else:
                return "", text

        else:
            return "", ""

    def handleDrop(self, action: str, data: str):
        if action == "clone":
            self.cloneDialog(data)
        elif action == "open":
            self.openRepo(data, exactMatch=False)
        elif action == "patch":
            rw = self.currentRepoWidget()
            if rw:
                rw.runTask(tasks.ApplyPatchFile, False, data)
            else:
                showInformation(self, self.tr("No repository"),
                                self.tr("Please open a repository before importing a patch."))
        else:
            log.warning("MainWindow", f"Unsupported drag-and-drop outcome {action}")

    # -------------------------------------------------------------------------
    # Prefs

    def refreshPrefs(self, prefDiff: dict = dict()):
        # Apply new style
        if "qtStyle" in prefDiff:
            settings.applyQtStylePref(forceApplyDefault=True)

        if "debug_verbosity" in prefDiff:
            log.setVerbosity(settings.prefs.debug_verbosity)

        if "language" in prefDiff:
            settings.applyLanguagePref()
            TaskBook.initialize()
            self.fillGlobalMenuBar()

        if "maxRecentRepos" in prefDiff:
            self.fillRecentMenu()

        self.statusBar2.setVisible(settings.prefs.showStatusBar)
        self.statusBar2.enableMemoryIndicator(settings.prefs.debug_showMemoryIndicator)

        self.tabs.refreshPrefs()
        self.autoHideMenuBar.refreshPrefs()
        for rw in self.tabs.widgets():
            rw.refreshPrefs()

    def onAcceptPrefsDialog(self, prefDiff: dict):
        # Early out if the prefs didn't change
        if not prefDiff:
            return

        # Apply changes from prefDiff to the actual prefs
        for k, v in prefDiff.items():
            settings.prefs.__dict__[k] = v

        # Write prefs to disk
        settings.prefs.write()

        # Notify widgets
        self.refreshPrefs(prefDiff)

        # Warn if changed any setting that requires a reload
        warnIfChanged = [
            "graph_chronologicalOrder",  # need to reload entire commit sequence
            "debug_hideStashJunkParents",  # need to change hidden commit cache, TODO: I guess this one is easy to do
            "diff_showStrayCRs",  # GF isn't able to re-render a single diff yet
            "diff_colorblindFriendlyColors",  # ditto
            "diff_largeFileThresholdKB",  # ditto
            "diff_imageFileThresholdKB",  # ditto
        ]

        warnIfNeedRestart = [
            "debug_forceQtApi",
        ]

        if any(k in warnIfNeedRestart for k in prefDiff):
            showInformation(
                self, self.tr("Apply Settings"),
                self.tr("You may need to restart {app} for all new settings to take effect.").format(app=qAppName()))
        elif any(k in warnIfChanged for k in prefDiff):
            showInformation(
                self, self.tr("Apply Settings"),
                self.tr("You may need to reload the current repository for all new settings to take effect."))

    def openPrefsDialog(self, focusOn: str = ""):
        dlg = PrefsDialog(self, focusOn)
        dlg.accepted.connect(lambda: self.onAcceptPrefsDialog(dlg.prefDiff))
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)  # don't leak dialog
        dlg.show()

    # -------------------------------------------------------------------------
    # Find

    def dispatchSearchCommand(self, op: Literal["start", "next", "previous"] = "start"):
        activeWindow = QApplication.activeWindow()
        if activeWindow is self and self.currentRepoWidget():
            self.currentRepoWidget().dispatchSearchCommand(op)
        elif isinstance(activeWindow, DiffView):
            activeWindow.search(op)
        else:
            QApplication.beep()
