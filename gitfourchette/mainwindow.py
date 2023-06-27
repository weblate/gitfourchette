import gc
import os
import re
from typing import Literal

import pygit2

from gitfourchette import log
from gitfourchette import settings
from gitfourchette import tasks
from gitfourchette.diffview.diffview import DiffView
from gitfourchette.exttools import openInTextEditor
from gitfourchette.forms.aboutdialog import showAboutDialog
from gitfourchette.forms.clonedialog import CloneDialog
from gitfourchette.forms.prefsdialog import PrefsDialog
from gitfourchette.forms.repostatusdisplay import RepoStatusDisplay
from gitfourchette.forms.welcomewidget import WelcomeWidget
from gitfourchette.globalshortcuts import GlobalShortcuts
from gitfourchette.qt import *
from gitfourchette.repostate import RepoState
from gitfourchette.repowidget import RepoWidget
from gitfourchette.toolbox import *


class Session:
    openTabs: list[str]
    activeTab: int
    geometry: QRect


class MainWindow(QMainWindow):
    styleSheetReloadScheduled = False

    welcomeStack: QStackedWidget
    welcomeWidget: WelcomeWidget
    tabs: CustomTabWidget
    recentMenu: QMenu
    repoMenu: QMenu
    memoryIndicator: MemoryIndicator

    def __init__(self):
        super().__init__()

        self.setObjectName("GFMainWindow")

        self.sharedSplitterStates = {}

        self.setWindowTitle(qAppName())
        self.resize(QSize(800, 600))
        self.move(QPoint(50, 50))

        self.tabs = CustomTabWidget(self)
        self.tabs.currentWidgetChanged.connect(self.onTabCurrentWidgetChanged)
        self.tabs.tabCloseRequested.connect(self.closeTab)
        self.tabs.tabContextMenuRequested.connect(self.onTabContextMenu)
        self.tabs.tabDoubleClicked.connect(self.onTabDoubleClicked)

        self.welcomeWidget = WelcomeWidget(self)

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

        self.statusDisplay = RepoStatusDisplay(self)
        self.memoryIndicator = MemoryIndicator(self)
        self.memoryIndicator.setVisible(False)

        self.statusBar = QStatusBar(self)
        self.statusBar.setSizeGripEnabled(False)
        self.statusBar.addPermanentWidget(self.statusDisplay, 1)
        self.statusBar.addPermanentWidget(self.memoryIndicator)
        self.setStatusBar(self.statusBar)

        self.setAcceptDrops(True)
        self.styleSheetReloadScheduled = False
        QApplication.instance().installEventFilter(self)

        self.refreshPrefs()

        QGuiApplication.instance().applicationStateChanged.connect(self.onApplicationStateChanged)

    def goBack(self):
        rw = self.currentRepoWidget()
        if rw:
            rw.navigateBack()

    def goForward(self):
        rw = self.currentRepoWidget()
        if rw:
            rw.navigateForward()

    @staticmethod
    def reloadStyleSheet():
        log.info("MainWindow", "Reloading QSS")
        with NonCriticalOperation("Reload application-wide stylesheet"):
            MainWindow.styleSheetReloadScheduled = False
            styleSheetFile = QFile("assets:style.qss")
            if not styleSheetFile.open(QFile.OpenModeFlag.ReadOnly):
                return
            styleSheet = styleSheetFile.readAll().data().decode("utf-8")
            QApplication.instance().setStyleSheet(styleSheet)
            styleSheetFile.close()

    def eventFilter(self, watched, event: QEvent):
        isPress = event.type() == QEvent.Type.MouseButtonPress
        isDblClick = event.type() == QEvent.Type.MouseButtonDblClick

        if event.type() == QEvent.Type.ThemeChange:
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
        if event.key() == Qt.Key.Key_Alt:
            self.autoHideMenuBar.toggle()

    def fillGlobalMenuBar(self):
        menubar = self.globalMenuBar
        menubar.clear()

        # -------------------------------------------------------------

        fileMenu = menubar.addMenu(self.tr("&File"))
        fileMenu.setObjectName("MWFileMenu")

        a = fileMenu.addAction(self.tr("&New Repository..."), self.newRepo)
        a.setShortcuts(QKeySequence.StandardKey.New)

        a = fileMenu.addAction(self.tr("C&lone Repository..."), self.cloneDialog)
        a.setShortcut("Ctrl+Shift+N")

        fileMenu.addSeparator()

        a = fileMenu.addAction(self.tr("&Open Repository..."), self.openDialog)
        a.setShortcuts(QKeySequence.StandardKey.Open)

        self.recentMenu = fileMenu.addMenu(self.tr("Open &Recent"))
        self.recentMenu.setObjectName("RecentMenu")

        a = fileMenu.addAction(self.tr("&Close Tab"), self.dispatchCloseCommand)
        a.setShortcuts(GlobalShortcuts.closeTab)

        fileMenu.addSeparator()

        a = fileMenu.addAction(self.tr("Apply Patch..."), self.importPatch)
        a.setShortcut("Ctrl+I")

        fileMenu.addAction(self.tr("Reverse Patch..."), self.importPatchReverse)

        fileMenu.addSeparator()

        a = fileMenu.addAction(self.tr("&Preferences..."), self.openPrefsDialog)
        a.setMenuRole(QAction.MenuRole.PreferencesRole)
        a.setShortcuts(QKeySequence.StandardKey.Preferences)

        a = fileMenu.addAction(self.tr("Set Up Git &Identity..."), self.setUpIdentity)
        a.setMenuRole(QAction.MenuRole.ApplicationSpecificRole)

        fileMenu.addSeparator()

        a = fileMenu.addAction(self.tr("&Quit"), self.close)
        a.setMenuRole(QAction.MenuRole.QuitRole)
        a.setShortcuts(QKeySequence.StandardKey.Quit)

        # -------------------------------------------------------------

        editMenu: QMenu = menubar.addMenu(self.tr("&Edit"))
        editMenu.setObjectName("MWEditMenu")

        a = editMenu.addAction(self.tr("&Find..."), lambda: self.dispatchSearchCommand("start"))
        a.setShortcuts(QKeySequence.StandardKey.Find)

        a = editMenu.addAction(self.tr("Find Next"), lambda: self.dispatchSearchCommand("next"))
        a.setShortcuts(QKeySequence.StandardKey.FindNext)

        a = editMenu.addAction(self.tr("Find Previous"), lambda: self.dispatchSearchCommand("previous"))
        a.setShortcuts(QKeySequence.StandardKey.FindPrevious)

        # -------------------------------------------------------------

        repoMenu: QMenu = menubar.addMenu(self.tr("&Repo"))
        repoMenu.setObjectName("MWRepoMenu")
        # repoMenu.setEnabled(False)
        self.repoMenu = repoMenu

        a = repoMenu.addAction(self.tr("&Refresh"), self.refreshRepo)
        a.setShortcuts(GlobalShortcuts.refresh)

        a = repoMenu.addAction(self.tr("&Hard Refresh"), self.hardRefresh)
        a.setShortcut("Ctrl+F5")

        repoMenu.addSeparator()

        a = repoMenu.addAction(self.tr("&Commit..."), self.commit)
        a.setShortcuts(GlobalShortcuts.commit)

        a = repoMenu.addAction(self.tr("&Amend Last Commit..."), self.amend)
        a.setShortcuts(GlobalShortcuts.amendCommit)

        a = repoMenu.addAction(self.tr("Stash Changes..."), self.newStash)
        a.setShortcuts(GlobalShortcuts.newStash)

        repoMenu.addSeparator()

        repoMenu.addAction(self.tr("Add Re&mote..."), self.newRemote)

        repoMenu.addSeparator()

        configFilesMenu = repoMenu.addMenu(self.tr("&Local Config Files"))

        a = repoMenu.addAction(self.tr("&Open Repo Folder"), self.openRepoFolder)
        a.setShortcuts(GlobalShortcuts.openRepoFolder)

        repoMenu.addAction(self.tr("Cop&y Repo Path"), self.copyRepoPath)
        repoMenu.addAction(self.tr("Rename Repo..."), self.renameRepo)
        repoMenu.addSeparator()
        repoMenu.addAction(self.tr("Resc&ue Discarded Changes..."), self.openRescueFolder)
        repoMenu.addAction(self.tr("Clear Discarded Changes..."), self.clearRescueFolder)
        repoMenu.addAction(self.tr("Recall Lost Commit..."), self.recallCommit)

        configFilesMenu.addAction(".gitignore", self.openGitignore)
        configFilesMenu.addAction("config", self.openLocalConfig)
        configFilesMenu.addAction("exclude", self.openLocalExclude)

        # -------------------------------------------------------------

        branchMenu = menubar.addMenu(self.tr("&Branch"))
        branchMenu.setObjectName("MWBranchMenu")

        a = branchMenu.addAction(self.tr("New &Branch..."), self.newBranch)
        a.setShortcuts(GlobalShortcuts.newBranch)

        a = branchMenu.addAction(self.tr("&Push Branch..."), self.push)
        a.setShortcuts(GlobalShortcuts.pushBranch)

        a = branchMenu.addAction(self.tr("&Fast-Forward to Remote Branch..."), self.fastForward)
        # a.setShortcuts(GlobalShortcuts.pullBranch)

        # -------------------------------------------------------------

        goMenu: QMenu = menubar.addMenu(self.tr("&Go"))
        goMenu.setObjectName("MWGoMenu")

        a = goMenu.addAction(self.tr("&Uncommitted Changes"), self.selectUncommittedChanges)
        a.setShortcut("Ctrl+U")

        goMenu.addSeparator()

        a = goMenu.addAction(self.tr("&Next Tab"), self.nextTab)
        a.setShortcut("Ctrl+Tab")

        a = goMenu.addAction(self.tr("&Previous Tab"), self.previousTab)
        a.setShortcut("Ctrl+Shift+Tab")

        goMenu.addSeparator()

        a = goMenu.addAction(self.tr("Next File"), self.nextFile)
        a.setShortcut("Ctrl+]")

        a = goMenu.addAction(self.tr("Previous File"), self.previousFile)
        a.setShortcut("Ctrl+[")

        goMenu.addSeparator()

        a = goMenu.addAction(self.tr("Navigate Back"), self.goBack)
        a.setShortcuts(GlobalShortcuts.navBack)

        a = goMenu.addAction(self.tr("Navigate Forward"), self.goForward)
        a.setShortcuts(GlobalShortcuts.navForward)

        if __debug__:
            a = goMenu.addAction(self.tr("Navigation Log"), lambda: print(self.currentRepoWidget().navHistory.getTextLog()))
            a.setShortcut("Alt+Down")

        # -------------------------------------------------------------

        helpMenu = menubar.addMenu(self.tr("&Help"))
        helpMenu.setObjectName("MWHelpMenu")

        a = helpMenu.addAction(self.tr("&About {0}").format(qAppName()), lambda: showAboutDialog(self))
        a.setMenuRole(QAction.AboutRole)

        # -------------------------------------------------------------

        self.fillRecentMenu()

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

        if any(k in warnIfChanged for k in prefDiff):
            showInformation(self, self.tr("Apply Settings"),
                            self.tr("You may need to reload the current repository for all new settings to take effect."))

    def openPrefsDialog(self, focusOn: str = ""):
        dlg = PrefsDialog(self, focusOn)
        dlg.accepted.connect(lambda: self.onAcceptPrefsDialog(dlg.prefDiff))
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)  # don't leak dialog
        dlg.show()

    def fillRecentMenu(self):
        def onClearRecents():
            settings.history.clearRepoHistory()
            settings.history.write()
            self.fillRecentMenu()

        self.recentMenu.clear()
        for historic in settings.history.getRecentRepoPaths(settings.prefs.maxRecentRepos):
            self.recentMenu.addAction(compactPath(historic), lambda path=historic: self.openRepo(path))
        self.recentMenu.addSeparator()
        self.recentMenu.addAction(self.tr("Clear"), onClearRecents)

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

        self.statusDisplay.install(w.statusDisplayCache)

        # If we don't have a RepoState, then the tab is lazy-loaded.
        # We need to load it now.
        if not w.isLoaded:
            # Disable tabs widget while we're loading the repo to prevent tabs
            # from accidentally being dragged while the UI is locking up
            with DisableWidgetContext(self.tabs):
                # Load repo
                success = self._loadRepo(w, w.workdir)
                if not success:
                    return
                settings.history.write()
        else:
            # Trigger repo refresh.
            w.onRegainFocus()

        w.refreshWindowTitle()

    def onTabContextMenu(self, globalPoint: QPoint, i: int):
        if i < 0:  # Right mouse button released outside tabs
            return
        rw: RepoWidget = self.tabs.widget(i)
        menu = QMenu(self)
        menu.setObjectName("MWRepoTabContextMenu")
        closeTabAction = menu.addAction(self.tr("Close Tab"), lambda: self.closeTab(i))
        menu.addAction(self.tr("Close Other Tabs"), lambda: self.closeOtherTabs(i))
        menu.addSeparator()
        openRepoFolderAction = menu.addAction(self.tr("Open Repo Folder"), lambda: self.openRepoFolder(rw))
        menu.addAction(self.tr("Copy Repo Path"), lambda: self.copyRepoPath(rw))
        menu.addAction(self.tr("Rename", "RepoTabCM"), lambda: self.renameRepo(rw))
        menu.addSeparator()
        if rw.state:
            menu.addAction(self.tr("Unload", "RepoTabCM"), lambda: self.unloadTab(i))
        else:
            menu.addAction(self.tr("Load", "RepoTabCM"), lambda: self.loadTab(i))

        if i == self.tabs.currentIndex():
            closeTabAction.setShortcuts(GlobalShortcuts.closeTab)
            openRepoFolderAction.setShortcuts(GlobalShortcuts.openRepoFolder)

        menu.exec(globalPoint)
        menu.deleteLater()

    def onTabDoubleClicked(self, i: int):
        if i < 0:
            return
        rw: RepoWidget = self.tabs.widget(i)
        if settings.prefs.tabs_doubleClickOpensFolder:
            self.openRepoFolder(rw)

    def _constructRepo(self, path: str):
        repo = pygit2.Repository(path)

        if repo.is_shallow:
            raise NotImplementedError(self.tr("Sorry, shallow repositories aren’t supported yet.").format(path))

        if repo.is_bare:
            raise NotImplementedError(self.tr("Sorry, bare repositories aren’t supported yet.").format(path))

        return repo

    def _loadRepo(self, rw: RepoWidget, pathOrRepo: str | pygit2.Repository):
        assert rw

        repo: pygit2.Repository
        path: str

        if type(pathOrRepo) is pygit2.Repository:
            repo = pathOrRepo
            path = repo.workdir
        elif type(pathOrRepo) is str:
            path = pathOrRepo
            repo = self._constructRepo(path)
        else:
            raise TypeError("pathOrRepo must either be an str or a Repository")

        assert repo is not None

        shortname = settings.history.getRepoNickname(path)

        progress = QProgressDialog(self.tr("Opening repository..."), self.tr("Abort"), 0, 0, self)
        progress.setWindowTitle(shortname)
        progress.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.CustomizeWindowHint | Qt.WindowType.WindowTitleHint)  # hide close button
        progress.setMinimumWidth(2 * progress.fontMetrics().horizontalAdvance("000,000,000 commits loaded."))
        progress.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)  # don't leak dialog

        # On macOS, WindowModal triggers a slow animation that makes loading a repo feel gratuitously sluggish.
        # ApplicationModal isn't as bad.
        modality = Qt.WindowModality.ApplicationModal if MACOS else Qt.WindowModality.WindowModal
        setWindowModal(progress, modality)

        if not settings.TEST_MODE:
            progress.show()
        QCoreApplication.processEvents()

        try:
            newState = RepoState(repo)
            commitSequence = newState.loadCommitSequence(progress)

            rw.setRepoState(newState)

            rw.graphView.setHiddenCommits(newState.hiddenCommits)
            rw.graphView.setCommitSequence(commitSequence)
            with QSignalBlockerContext(rw.sidebar):
                rw.sidebar.refresh(newState)

            self.refreshTabText(rw)

        except BaseException as exc:
            # In test mode, we really want this to fail
            if settings.TEST_MODE:
                raise exc

            excMessageBox(
                exc,
                message=self.tr("An exception was raised while opening “{0}”").format(escape(path)),
                parent=self)
            return False

        finally:
            progress.close()

        settings.history.setRepoNumCommits(repo.workdir, len(commitSequence))

        rw.graphView.selectUncommittedChanges(force=True)

        # Scrolling HEAD into view isn't super intuitive if we boot to Uncommitted Changes
        # if newState.activeCommitOid:
        #     rw.graphView.scrollToCommit(newState.activeCommitOid, QAbstractItemView.ScrollHint.PositionAtCenter)

        # rw.saveFilePositions()
        return True

    def _openRepo(self, path: str, foreground=True, addToHistory=True, tabIndex=-1
                  ) -> RepoWidget | None:
        # Construct a pygit2.Repository so we can get the workdir
        repo = self._constructRepo(path)

        if not repo:
            return None

        workdir = repo.workdir

        # First check that we don't have a tab for this repo already
        for i in range(self.tabs.count()):
            existingRW: RepoWidget = self.tabs.widget(i)
            if os.path.samefile(workdir, existingRW.workdir):
                repo.free()
                del repo
                self.tabs.setCurrentIndex(i)
                return existingRW

        newRW = RepoWidget(self, self.sharedSplitterStates)

        if foreground:
            if not self._loadRepo(newRW, repo):
                newRW.destroy()
                return None  # don't create the tab if opening the repo failed
        else:
            newRW.setPendingWorkdir(workdir)
            repo.free()
            del repo

        tabIndex = self.tabs.insertTab(tabIndex, newRW, newRW.getTitle())
        self.tabs.setTabTooltip(tabIndex, compactPath(workdir))

        if foreground:
            self.tabs.setCurrentIndex(tabIndex)

        newRW.nameChange.connect(lambda: self.refreshTabText(newRW))
        newRW.openRepo.connect(lambda path: self.openRepoNextTo(newRW, path))
        newRW.openPrefs.connect(self.openPrefsDialog)

        if addToHistory:
            settings.history.addRepo(workdir)
            settings.history.write()
            self.fillRecentMenu()

        return newRW

    # -------------------------------------------------------------------------

    def onApplicationStateChanged(self, state: Qt.ApplicationState):
        rw = self.currentRepoWidget()
        if rw and state == Qt.ApplicationState.ApplicationActive and settings.prefs.debug_autoRefresh:
            rw.onRegainFocus()

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
                                self.tr("Please open a repository before triggering this operation."))
        return wrapper

    @needRepoWidget
    def refreshRepo(self, rw: RepoWidget):
        rw.refreshRepo()

    @needRepoWidget
    def hardRefresh(self, rw: RepoWidget):
        self._loadRepo(rw, rw.workdir)

    @needRepoWidget
    def openRepoFolder(self, rw: RepoWidget):
        showInFolder(rw.workdir)

    @needRepoWidget
    def copyRepoPath(self, rw: RepoWidget):
        QApplication.clipboard().setText(rw.workdir)

    @needRepoWidget
    def commit(self, rw: RepoWidget):
        rw.runTask(tasks.NewCommit)

    @needRepoWidget
    def amend(self, rw: RepoWidget):
        rw.runTask(tasks.AmendCommit)

    @needRepoWidget
    def newStash(self, rw: RepoWidget):
        rw.runTask(tasks.NewStash)

    @needRepoWidget
    def newBranch(self, rw: RepoWidget):
        rw.runTask(tasks.NewBranchFromHead)

    @needRepoWidget
    def newRemote(self, rw: RepoWidget):
        rw.runTask(tasks.NewRemote)

    @needRepoWidget
    def renameRepo(self, rw: RepoWidget):
        rw.renameRepo()

    @needRepoWidget
    def push(self, rw: RepoWidget):
        rw.startPushFlow()

    @needRepoWidget
    def fastForward(self, rw: RepoWidget):
        rw.runTask(tasks.FastForwardBranch)

    @needRepoWidget
    def openRescueFolder(self, rw: RepoWidget):
        rw.openRescueFolder()

    @needRepoWidget
    def clearRescueFolder(self, rw: RepoWidget):
        rw.clearRescueFolder()

    @needRepoWidget
    def recallCommit(self, rw: RepoWidget):
        rw.recallCommit()

    @needRepoWidget
    def setUpIdentity(self, rw: RepoWidget):
        rw.setUpRepoIdentity()

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
    # File menu callbacks

    def newRepo(self):
        def proceed(path: str):
            try:
                pygit2.init_repository(path)
                self.openRepo(path)
            except BaseException as exc:
                excMessageBox(
                    exc,
                    self.tr("New repository"),
                    self.tr("Couldn’t create an empty repository in “{0}”.").format(escape(path)),
                    parent=self,
                    icon='warning')

        qfd = PersistentFileDialog.saveFile(self, "NewRepo", self.tr("New repository"))
        qfd.fileSelected.connect(proceed)
        qfd.show()

    def cloneDialog(self, initialUrl: str = ""):
        dlg = CloneDialog(initialUrl, self)

        dlg.cloneSuccessful.connect(lambda path: self.openRepo(path))

        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        setWindowModal(dlg)
        dlg.show()

    def openDialog(self):
        qfd = PersistentFileDialog.openDirectory(self, "NewRepo", self.tr("Open repository"))
        qfd.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)  # don't leak dialog
        qfd.fileSelected.connect(self.openRepo)
        qfd.show()

    def openRepo(self, path):
        try:
            rw = self._openRepo(path)
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

    @needRepoWidget
    def importPatch(self, rw: RepoWidget):
        rw.runTask(tasks.ApplyPatchFile, False)

    @needRepoWidget
    def importPatchReverse(self, rw: RepoWidget):
        rw.runTask(tasks.ApplyPatchFile, True)

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
        self._loadRepo(rw, rw.workdir)

    def openRepoNextTo(self, rw, path: str):
        index = self.tabs.indexOf(rw)
        if index >= 0:
            index += 1
        return self._openRepo(path, tabIndex=index)

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
    # Go menu

    def selectUncommittedChanges(self):
        self.currentRepoWidget().graphView.selectUncommittedChanges()

    def nextFile(self):
        self.currentRepoWidget().selectNextFile(True)

    def previousFile(self):
        self.currentRepoWidget().selectNextFile(False)

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
                    newRepoWidget = self._openRepo(path, foreground=False, addToHistory=False)
                    successfulRepos.append(path)
                except (pygit2.GitError, OSError, NotImplementedError) as exc:
                    # GitError: most errors thrown by pygit2
                    # OSError: e.g. permission denied
                    # NotImplementedError: e.g. shallow/bare repos
                    errors.append((path, exc))
                    continue

                if i == session.activeTabIndex and newRepoWidget is not None:
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
        self.saveSession()

        # Close all tabs so RepoWidgets release all their resources.
        # Important so unit tests wind down properly!
        self.closeAllTabs()

        e.accept()

    # -------------------------------------------------------------------------
    # Drag and drop

    @staticmethod
    def getDropOutcomeFromMimeData(mime: QMimeData) -> tuple[Literal["", "open", "clone"], str]:
        if mime.hasUrls() and len(mime.urls()) > 0:
            url: QUrl = mime.urls()[0]
            if url.isLocalFile():
                if url.path().endswith(".patch"):
                    return "patch", url.toLocalFile()
                else:
                    return "open", url.toLocalFile()
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

    def dragEnterEvent(self, event: QDragEnterEvent):
        action, data = self.getDropOutcomeFromMimeData(event.mimeData())
        if action:
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        action, data = self.getDropOutcomeFromMimeData(event.mimeData())
        if action == "clone":
            event.setAccepted(True)  # keep dragged item from coming back to cursor on macOS
            self.cloneDialog(data)
        elif action == "open":
            event.setAccepted(True)  # keep dragged item from coming back to cursor on macOS
            self.openRepo(data)
        elif action == "patch":
            event.setAccepted(True)  # keep dragged item from coming back to cursor on macOS
            rw = self.currentRepoWidget()
            if rw:
                print("Import patch", data)
                rw.runTask(tasks.ApplyPatchFile, False, data)
                # self.importPatch(rw, data)
            else:
                showInformation(self, self.tr("No repository"),
                                self.tr("Please open a repository before importing a patch."))
        else:
            log.warning("MainWindow", f"Unsupported drag-and-drop outcome {action}")

    # -------------------------------------------------------------------------
    # Refresh prefs

    def refreshPrefs(self, prefDiff: dict = dict()):
        # Apply new style
        if "qtStyle" in prefDiff:
            settings.applyQtStylePref(forceApplyDefault=True)

        if "debug_verbosity" in prefDiff:
            log.setVerbosity(settings.prefs.debug_verbosity)

        if "language" in prefDiff:
            settings.applyLanguagePref()
            self.fillGlobalMenuBar()

        if "maxRecentRepos" in prefDiff:
            self.fillRecentMenu()

        self.statusBar.setVisible(settings.prefs.showStatusBar)
        self.memoryIndicator.setVisible(settings.prefs.debug_showMemoryIndicator)

        self.tabs.refreshPrefs()
        self.autoHideMenuBar.refreshPrefs()
        for rw in self.tabs.widgets():
            rw.refreshPrefs()

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
