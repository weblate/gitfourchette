from gitfourchette import settings
from gitfourchette.globalstatus import globalstatus
from gitfourchette.qt import *
from gitfourchette.repostate import RepoState
from gitfourchette.util import (compactPath, showInFolder, excMessageBox, DisableWidgetContext, QSignalBlockerContext)
from gitfourchette.widgets.aboutdialog import showAboutDialog
from gitfourchette.widgets.autohidemenubar import AutoHideMenuBar
from gitfourchette.widgets.clonedialog import CloneDialog
from gitfourchette.widgets.customtabwidget import CustomTabWidget
from gitfourchette.widgets.prefsdialog import PrefsDialog
from gitfourchette.widgets.repowidget import RepoWidget
from typing import Literal
import gc
import os
import pygit2
import re


try:
    import psutil
except ImportError:
    print("psutil isn't available. The memory indicator will not work.")
    psutil = None


class Session:
    openTabs: list[str]
    activeTab: int
    geometry: QRect


class MainWindow(QMainWindow):
    tabs: CustomTabWidget
    recentMenu: QMenu
    repoMenu: QMenu

    def __init__(self):
        super().__init__()

        self.setObjectName("GFMainWindow")

        self.sharedSplitterStates = {}

        self.setWindowTitle(QApplication.applicationDisplayName())
        self.resize(QSize(800, 600))
        self.move(QPoint(50, 50))

        self.tabs = CustomTabWidget(self)
        self.tabs.stacked.currentChanged.connect(self.onTabChange)
        self.tabs.tabCloseRequested.connect(self.closeTab)
        self.tabs.tabContextMenuRequested.connect(self.onTabContextMenu)
        self.setCentralWidget(self.tabs)

        menuBar = self.makeMenu()
        self.setMenuBar(menuBar)
        self.autoHideMenuBar = AutoHideMenuBar(menuBar)

        self.statusProgress = QProgressBar()
        self.statusProgress.setMaximumHeight(16)
        self.statusProgress.setMaximumWidth(128)
        self.statusProgress.setVisible(False)
        self.statusProgress.setTextVisible(False)
        globalstatus.statusText.connect(self.updateStatusMessage)
        globalstatus.progressMaximum.connect(lambda v: self.statusProgress.setMaximum(v))
        globalstatus.progressValue.connect(lambda v: [self.statusProgress.setVisible(True), self.statusProgress.setValue(v)])
        globalstatus.progressDisable.connect(lambda: self.statusProgress.setVisible(False))
        self.statusBar = QStatusBar()
        self.statusBar.setSizeGripEnabled(False)
        self.statusBar.addPermanentWidget(self.statusProgress)
        if settings.prefs.debug_showMemoryIndicator:
            self.memoryIndicator = QPushButton("Mem")
            self.memoryIndicator.setMaximumHeight(16)
            self.memoryIndicator.setMinimumWidth(128)
            self.memoryIndicator.clicked.connect(lambda e: self.onMemoryIndicatorClicked())
            self.memoryIndicator.setToolTip("Force GC")
            self.statusBar.addPermanentWidget(self.memoryIndicator)
        else:
            self.memoryIndicator = None
        if settings.prefs.showStatusBar:
            self.setStatusBar(self.statusBar)

        self.setAcceptDrops(True)

        qApp.installEventFilter(self)

    def eventFilter(self, watched, event: QEvent):
        isPress = event.type() == QEvent.MouseButtonPress
        isDblClick = event.type() == QEvent.MouseButtonDblClick

        if (isPress or isDblClick) and self.isActiveWindow():
            mouseEvent: QMouseEvent = event

            isBack = mouseEvent.button() == Qt.BackButton
            isForward = mouseEvent.button() == Qt.ForwardButton

            if isBack or isForward:
                if isPress:
                    rw = self.currentRepoWidget()
                    if rw and isBack:
                        rw.navigateBack()
                    elif rw and isForward:
                        rw.navigateForward()

                # eat navigation clicks or double-clicks
                return True

        return False

    def onMemoryIndicatorClicked(self):
        gc.collect()

        print("Top-Level Windows:")
        for tlw in QApplication.topLevelWindows():
            print("*", tlw)
        print("Top-Level Widgets:")
        for tlw in QApplication.topLevelWidgets():
            print("*", tlw, tlw.objectName())
        print()

        self.updateMemoryIndicator()

    def updateMemoryIndicator(self):
        nChildren = len(self.findChildren(QObject))
        if psutil:
            rss = psutil.Process(os.getpid()).memory_info().rss
            self.memoryIndicator.setText(F"{rss // 1024:,}K {nChildren}Q")
        else:
            self.memoryIndicator.setText(F"{nChildren}Q")

    def updateStatusMessage(self, message):
        self.statusBar.showMessage(message)
        #QCoreApplication.processEvents() # bad idea -- this may cause a tower of nested calls
        # where loadCommitAsync -> loadDiffAsync -> loadCommitAsync -> loadDiffAsync...

    def paintEvent(self, event:QPaintEvent):
        if self.memoryIndicator:
            self.updateMemoryIndicator()
        super().paintEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Alt:
            self.autoHideMenuBar.toggle()

    def makeMenu(self) -> QMenuBar:
        menubar = QMenuBar(self)
        menubar.setObjectName("MWMenuBar")

        fileMenu = menubar.addMenu("&File")
        fileMenu.setObjectName("MWFileMenu")
        fileMenu.addAction("&New Repository...", self.newRepo, QKeySequence.New)
        fileMenu.addAction("Cl&one Repository...", self.cloneDialog, QKeySequence("Ctrl+Shift+N"))
        fileMenu.addSeparator()
        fileMenu.addAction("&Open Repository...", self.openDialog, QKeySequence.Open)
        self.recentMenu = fileMenu.addMenu("Open &Recent")
        self.recentMenu.setObjectName("RecentMenu")
        fileMenu.addAction("&Close Tab", self.closeCurrentTab, QKeySequence.Close)
        fileMenu.addSeparator()
        fileMenu.addAction("&Preferences...", self.openSettings, QKeySequence.Preferences)
        fileMenu.addSeparator()
        fileMenu.addAction("&Quit", self.close, QKeySequence.Quit)

        repoMenu: QMenu = menubar.addMenu("&Repo")
        repoMenu.setObjectName("MWRepoMenu")
        repoMenu.addAction("&Refresh", self.quickRefresh, QKeySequence.Refresh)
        repoMenu.addAction("&Hard Refresh", self.refresh, QKeySequence("Ctrl+F5"))
        repoMenu.addSeparator()
        repoMenu.addAction("&Commit...", self.commit, QKeySequence("Ctrl+K"))
        repoMenu.addAction("&Amend Last Commit...", self.amend, QKeySequence("Ctrl+Shift+K"))
        repoMenu.addSeparator()
        repoMenu.addAction("New &Branch...", self.newBranch, QKeySequence("Ctrl+B"))
        repoMenu.addAction("&Push Branch...", self.push, QKeySequence("Ctrl+P"))
        repoMenu.addSeparator()
        repoMenu.addAction("New Remote...", self.newRemote)
        repoMenu.addSeparator()
        repoMenu.addAction("&Find Commit...", lambda: self.currentRepoWidget().findFlow(), QKeySequence.Find)
        repoMenu.addAction("Find Next", lambda: self.currentRepoWidget().findNext(), QKeySequence.FindNext)
        repoMenu.addAction("Find Previous", lambda: self.currentRepoWidget().findPrevious(), QKeySequence.FindPrevious)
        repoMenu.addSeparator()
        configFilesMenu = repoMenu.addMenu("&Local Config Files")
        repoMenu.addAction("&Open Repo Folder", self.openRepoFolder, QKeySequence("Ctrl+Shift+O"))
        repoMenu.addAction("Cop&y Repo Path", self.copyRepoPath)
        repoMenu.addAction("Rename Repo...", self.renameRepo)
        repoMenu.addSeparator()
        repoMenu.addAction("Resc&ue Discarded Changes...", self.openRescueFolder)
        repoMenu.addAction("Clear Discarded Changes...", self.clearRescueFolder)
        repoMenu.setEnabled(False)
        self.repoMenu = repoMenu

        configFilesMenu.addAction(".gitignore", self.openGitignore)
        configFilesMenu.addAction("config", self.openLocalConfig)
        configFilesMenu.addAction("exclude", self.openLocalExclude)

        patchMenu = menubar.addMenu("&Patch")
        patchMenu.setObjectName("MWPatchMenu")
        patchMenu.addAction("&Find in Patch...", lambda: self.currentRepoWidget().findInDiffFlow(), QKeySequence("Ctrl+Alt+F"))

        goMenu: QMenu = menubar.addMenu("&Go")
        goMenu.setObjectName("MWGoMenu")
        goMenu.addAction("&Uncommitted Changes", self.selectUncommittedChanges, QKeySequence("Ctrl+U"))
        goMenu.addSeparator()
        goMenu.addAction("&Next Tab", self.nextTab, QKeySequence("Ctrl+Tab"))
        goMenu.addAction("&Previous Tab", self.previousTab, QKeySequence("Ctrl+Shift+Tab"))
        #asyncDelay = QAction("Fake &Async Delay", debugMenu)
        #asyncDelay.setCheckable(True)
        #asyncDelay.connect(...)
        #debugMenu.addAction(asyncDelay)

        helpMenu = menubar.addMenu("&Help")
        helpMenu.setObjectName("MWHelpMenu")
        helpMenu.addAction(F"&About {QApplication.applicationDisplayName()}", lambda: showAboutDialog(self))

        self.fillRecentMenu()

        return menubar

    def onAcceptPrefsDialog(self, dlg: PrefsDialog):
        if not dlg.prefDiff:  # No changes were made to the prefs
            return

        # Apply changes from prefDiff to the actual prefs
        for k in dlg.prefDiff:
            settings.prefs.__dict__[k] = dlg.prefDiff[k]

        # Write prefs to disk
        settings.prefs.write()

        # Notify widgets
        self.tabs.refreshPrefs()
        self.autoHideMenuBar.refreshPrefs()

        QMessageBox.warning(
            self,
            "Apply Settings",
            F"Some changes may require restarting {QApplication.applicationDisplayName()} to take effect.")

    def openSettings(self):
        dlg = PrefsDialog(self)
        dlg.accepted.connect(lambda: self.onAcceptPrefsDialog(dlg))
        dlg.setAttribute(Qt.WA_DeleteOnClose)  # don't leak dialog
        dlg.show()

    def fillRecentMenu(self):
        def onClearRecents():
            settings.history.clearRepoHistory()
            self.fillRecentMenu()

        self.recentMenu.clear()
        for historic in list(reversed(settings.history.history))[:settings.prefs.maxRecentRepos]:
            self.recentMenu.addAction(
                F"{settings.history.getRepoNickname(historic)} [{compactPath(historic)}]",
                lambda h=historic: self.openRepo(h))
        self.recentMenu.addSeparator()
        self.recentMenu.addAction("Clear", onClearRecents)

    def currentRepoWidget(self) -> RepoWidget:
        return self.tabs.currentWidget()

    def onTabChange(self, i):
        if i < 0:
            self.setWindowTitle(QApplication.applicationDisplayName())
            return

        self.repoMenu.setEnabled(False)
        w = self.currentRepoWidget()
        w.restoreSplitterStates()

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

        self.repoMenu.setEnabled(True)
        w.refreshWindowTitle()

    def onTabContextMenu(self, globalPoint: QPoint, i: int):
        if i < 0:  # Right mouse button released outside tabs
            return
        rw: RepoWidget = self.tabs.stacked.widget(i)
        menu = QMenu(self)
        menu.setObjectName("MWRepoTabContextMenu")
        menu.addAction("Close Tab", lambda: self.closeTab(i))
        menu.addAction("Close Other Tabs", lambda: self.closeOtherTabs(i))
        menu.addSeparator()
        menu.addAction("Open Repo Folder", lambda: self.openRepoFolder(rw))
        menu.addAction("Copy Repo Path", lambda: self.copyRepoPath(rw))
        menu.addAction("Rename", lambda: self.renameRepo(rw))
        menu.addSeparator()
        if rw.state:
            menu.addAction("Unload", lambda: self.unloadTab(i))
        else:
            menu.addAction("Load", lambda: self.loadTab(i))
        menu.exec_(globalPoint)

    def _constructRepo(self, path: str):
        try:
            repo = pygit2.Repository(path)

        except pygit2.GitError as gitError:
            qmb = QMessageBox(QMessageBox.Warning, "Open repository",
                              F"Couldn’t open “{path}”.\n\n{gitError}", parent=self)
            qmb.setAttribute(Qt.WA_DeleteOnClose)  # don't leak dialog
            qmb.show()
            return None

        if repo.is_shallow:
            qmb = QMessageBox(QMessageBox.Warning, "Shallow repository",
                              "Sorry, shallow repositories aren’t supported yet.", parent=self)
            qmb.setAttribute(Qt.WA_DeleteOnClose)  # don't leak dialog
            qmb.show()
            return None

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
        progress = QProgressDialog("Opening repository.", "Abort", 0, 0, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setWindowTitle(shortname)
        progress.setWindowFlags(Qt.Dialog)
        progress.setMinimumWidth(2 * progress.fontMetrics().horizontalAdvance("000,000,000 commits loaded."))
        QCoreApplication.processEvents()
        progress.setAttribute(Qt.WA_DeleteOnClose)  # don't leak dialog
        if not settings.TEST_MODE:
            progress.show()
        QCoreApplication.processEvents()

        try:
            newState = RepoState(repo)
            commitSequence = newState.loadCommitSequence(progress)

            rw.state = newState
            rw.actionFlows.repo = newState.repo

            rw.graphView.setCommitSequence(commitSequence)
            rw.sidebar.refresh(newState.repo)

            self.refreshTabText(rw)

        except BaseException as exc:
            excMessageBox(exc, message=F"An exception was thrown while opening “{path}”", parent=self)
            return False

        finally:
            progress.close()

        rw.graphView.selectUncommittedChanges()
        return True

    def openRepo(self, path: str, foreground=True, addToHistory=True) -> RepoWidget | None:
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
                self.tabs.setCurrentIndex(i)
                return existingRW

        newRW = RepoWidget(self, self.sharedSplitterStates)

        if foreground:
            if not self._loadRepo(newRW, repo):
                newRW.destroy()
                return None  # don't create the tab if opening the repo failed
        else:
            newRW.setPendingWorkdir(workdir)

        tabIndex = self.tabs.addTab(newRW, newRW.getTitle(), compactPath(workdir))

        if foreground:
            self.tabs.setCurrentIndex(tabIndex)

        newRW.nameChange.connect(lambda: self.refreshTabText(newRW))

        if addToHistory:
            settings.history.addRepo(workdir)
            self.fillRecentMenu()

        return newRW

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
                QApplication.beep()
        return wrapper

    @needRepoWidget
    def quickRefresh(self, rw: RepoWidget):
        rw.quickRefresh()

    @needRepoWidget
    def refresh(self, rw: RepoWidget):
        self._loadRepo(rw, rw.workdir)

    @needRepoWidget
    def openRepoFolder(self, rw: RepoWidget):
        showInFolder(rw.workdir)

    @needRepoWidget
    def copyRepoPath(self, rw: RepoWidget):
        QApplication.clipboard().setText(rw.workdir)

    @needRepoWidget
    def commit(self, rw: RepoWidget):
        rw.startCommitFlow()

    @needRepoWidget
    def amend(self, rw: RepoWidget):
        rw.actionFlows.amendFlow()

    @needRepoWidget
    def newBranch(self, rw: RepoWidget):
        rw.actionFlows.newBranchFlow()

    @needRepoWidget
    def newRemote(self, rw: RepoWidget):
        rw.actionFlows.newRemoteFlow()

    @needRepoWidget
    def renameRepo(self, rw: RepoWidget):
        rw.renameRepo()

    @needRepoWidget
    def push(self, rw: RepoWidget):
        rw.actionFlows.pushFlow()

    @needRepoWidget
    def openRescueFolder(self, rw: RepoWidget):
        rw.openRescueFolder()

    @needRepoWidget
    def clearRescueFolder(self, rw: RepoWidget):
        rw.clearRescueFolder()

    @needRepoWidget
    def openGitignore(self, rw: RepoWidget):
        QDesktopServices.openUrl(QUrl.fromLocalFile(rw.repo.workdir + ".gitignore"))

    @needRepoWidget
    def openLocalConfig(self, rw: RepoWidget):
        QDesktopServices.openUrl(QUrl.fromLocalFile(rw.repo.path + "/config"))

    @needRepoWidget
    def openLocalExclude(self, rw: RepoWidget):
        QDesktopServices.openUrl(QUrl.fromLocalFile(rw.repo.path + "/info/exclude"))

    # -------------------------------------------------------------------------
    # File menu callbacks

    def newRepo(self):
        path, _ = QFileDialog.getSaveFileName(self, "New repository")
        if path:
            pygit2.init_repository(path)
            self.openRepo(path)

    def cloneDialog(self, initialUrl: str = ""):
        dlg = CloneDialog(initialUrl, self)

        def onSuccess(path: str):
            self.openRepo(path)
            self.saveSession()
        dlg.cloneSuccessful.connect(onSuccess)

        dlg.setAttribute(Qt.WA_DeleteOnClose)
        dlg.show()

    def openDialog(self):
        path = settings.history.openFileDialogLastPath
        path = QFileDialog.getExistingDirectory(self, "Open repository", path)
        if path:
            settings.history.openFileDialogLastPath = path
            settings.history.write()
            self.openRepo(path)
            self.saveSession()

    # -------------------------------------------------------------------------
    # Tab management

    def closeCurrentTab(self):
        self.closeTab(self.tabs.currentIndex())

    def closeTab(self, index: int, collect: bool = True):
        self.tabs.widget(index).cleanup()
        self.tabs.removeTab(index, destroy=True)
        gc.collect()

    def closeOtherTabs(self, index: int):
        # First, set this tab as active so an active tab that gets closed doesn't trigger other tabs to load.
        self.tabs.setCurrentIndex(index)

        # Now close all tabs in reverse order but skip the index we want to keep.
        start = self.tabs.count()-1
        for i in range(start, -1, -1):
            if i != index:
                self.closeTab(i, False)

        gc.collect()

    def refreshTabText(self, rw):
        index = self.tabs.stacked.indexOf(rw)
        self.tabs.tabs.setTabText(index, rw.getTitle())

    def unloadTab(self, index: int):
        rw : RepoWidget = self.tabs.widget(index)
        rw.cleanup()
        gc.collect()
        self.refreshTabText(rw)

    def loadTab(self, index: int):
        rw : RepoWidget = self.tabs.widget(index)
        self._loadRepo(rw, rw.workdir)

    def nextTab(self):
        if self.tabs.count() == 0:
            QApplication.beep()
            return
        index = self.tabs.currentIndex()
        index += 1
        index %= self.tabs.count()
        self.tabs.tabs.setCurrentIndex(index)

    def previousTab(self):
        if self.tabs.count() == 0:
            QApplication.beep()
            return
        index = self.tabs.currentIndex()
        index += self.tabs.count() - 1
        index %= self.tabs.count()
        self.tabs.tabs.setCurrentIndex(index)

    # -------------------------------------------------------------------------
    # Go menu

    def selectUncommittedChanges(self):
        self.currentRepoWidget().graphView.selectUncommittedChanges()

    # -------------------------------------------------------------------------
    # Session management

    def restoreSession(self, session: settings.Session):
        self.sharedSplitterStates = {k: settings.decodeBinary(session.splitterStates[k]) for k in session.splitterStates}
        self.restoreGeometry(settings.decodeBinary(session.windowGeometry))

        # Stop here if there are no tabs to load
        if not session.tabs:
            return

        # Normally, changing the current tab will load the corresponding repo in the background.
        # But we don't want to load every repo as we're creating tabs, so temporarily disconnect the signal.
        with QSignalBlockerContext(self.tabs.stacked):
            # We might not be able to load all tabs, so we may have to adjust session.activeTabIndex.
            activeTab = -1

            # Lazy-loading: prepare all tabs, but don't load the repos (foreground=False).
            for i, path in enumerate(session.tabs):
                newRepoWidget = self.openRepo(path, foreground=False)
                if i == session.activeTabIndex and newRepoWidget is not None:
                    activeTab = self.tabs.count()-1

            # Set current tab and load its repo.
            if activeTab >= 0:
                self.tabs.setCurrentIndex(session.activeTabIndex)
                self.onTabChange(session.activeTabIndex)

    def saveSession(self):
        session = settings.Session()
        session.windowGeometry = settings.encodeBinary(self.saveGeometry())
        if self.currentRepoWidget():
            session.splitterStates = {s.objectName(): settings.encodeBinary(s.saveState()) for s in self.currentRepoWidget().splittersToSave}
        else:
            session.splitterStates = {}
        session.tabs = [self.tabs.widget(i).workdir for i in range(self.tabs.count())]
        session.activeTabIndex = self.tabs.currentIndex()
        session.write()

    def closeEvent(self, e):
        qApp.removeEventFilter(self)
        self.saveSession()
        e.accept()

    # -------------------------------------------------------------------------
    # Drag and drop

    @staticmethod
    def getDropOutcomeFromMimeData(mime: QMimeData) -> tuple[Literal["", "open", "clone"], str]:
        if mime.hasUrls() and len(mime.urls()) > 0:
            url: QUrl = mime.urls()[0]
            if url.isLocalFile():
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
            self.cloneDialog(data)
        elif action == "open":
            self.openRepo(data)
