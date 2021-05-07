from allqt import *
from dialogs.prefsdialog import PrefsDialog
from globalstatus import globalstatus
from repostate import RepoState
from util import compactSystemPath, showInFolder, excMessageBox, DisableWidgetContext
from widgets.customtabwidget import CustomTabWidget
from widgets.repowidget import RepoWidget
import gc
import git
import os
import pickle
import settings
import zlib


try:
    import psutil
except ImportError:
    print("psutil isn't available. The memory indicator will not work.")
    psutilAvailable = False
else:
    psutilAvailable = True


class Session:
    openTabs: list[str]
    activeTab: int
    geometry: QRect


class MainWindow(QMainWindow):
    tabs: CustomTabWidget

    def __init__(self):
        super().__init__()

        self.sharedSplitterStates = {}

        self.setWindowTitle(settings.PROGRAM_NAME)
        self.setWindowIcon(QIcon("icons/gf.png"))
        self.resize(QSize(800, 600))
        self.move(QPoint(50, 50))

        self.tabs = CustomTabWidget(self)
        self.tabs.stacked.currentChanged.connect(self.onTabChange)
        self.tabs.tabCloseRequested.connect(self.closeTab)
        self.tabs.tabContextMenuRequested.connect(self.onTabContextMenu)
        self.setCentralWidget(self.tabs)

        self.makeMenu()

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
            self.memoryIndicator.clicked.connect(lambda e: [gc.collect(), print("GC!"), self.updateMemoryIndicator()])
            self.memoryIndicator.setToolTip("Force GC")
            self.statusBar.addPermanentWidget(self.memoryIndicator)
        else:
            self.memoryIndicator = None
        if settings.prefs.showStatusBar:
            self.setStatusBar(self.statusBar)

        self.initialChildren = list(self.findChildren(QObject))

    def updateMemoryIndicator(self):
        nChildren = len(self.findChildren(QObject))
        if psutilAvailable:
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

    def makeMenu(self):
        menubar = QMenuBar()

        fileMenu = menubar.addMenu("&File")
        fileMenu.addAction("&Open", self.openDialog, QKeySequence.Open)
        self.recentMenu = fileMenu.addMenu("Open &Recent")
        fileMenu.addAction("&Close Tab", self.closeCurrentTab, QKeySequence.Close)
        fileMenu.addSeparator()
        fileMenu.addAction("&Settings...", self.openSettings, QKeySequence.Preferences)
        fileMenu.addSeparator()
        fileMenu.addAction("&Quit", self.close, QKeySequence.Quit)

        repoMenu = menubar.addMenu("&Repo")
        repoMenu.addAction("&Refresh", self.quickRefresh, QKeySequence.Refresh)
        repoMenu.addAction("Open Repo Folder", self.openRepoFolder)
        repoMenu.addSeparator()
        repoMenu.addAction("Commit...", lambda: self.currentRepoWidget().commitFlow(), QKeySequence(Qt.CTRL + Qt.Key_K))
        repoMenu.addAction("Amend Last Commit...", lambda: self.currentRepoWidget().amendFlow(), QKeySequence(Qt.CTRL + Qt.SHIFT + Qt.Key_K))
        repoMenu.addSeparator()
        repoMenu.addAction("Push Active Branch...", lambda: self.currentRepoWidget().push())
        repoMenu.addAction("Rename...", lambda: self.currentRepoWidget().renameRepo())
        repoMenu.addSeparator()
        repoMenu.addAction("&Find...", lambda: self.currentRepoWidget().findFlow(), QKeySequence.Find)
        repoMenu.addAction("Find Next", lambda: self.currentRepoWidget().findNext(), QKeySequence.FindNext)
        repoMenu.addAction("Find Previous", lambda: self.currentRepoWidget().findPrevious(), QKeySequence.FindPrevious)

        goMenu:QMenu = menubar.addMenu("&Go")
        goMenu.addAction("&Uncommitted Changes", self.selectUncommittedChanges, QKeySequence(Qt.CTRL + Qt.Key_U))
        goMenu.addSeparator()
        goMenu.addAction("&Next Tab", self.nextTab, QKeySequence(Qt.CTRL + Qt.Key_Tab))
        goMenu.addAction("&Previous Tab", self.previousTab, QKeySequence(Qt.CTRL + Qt.SHIFT + Qt.Key_Tab))

        if settings.prefs.debug_showDebugMenu:
            debugMenu = menubar.addMenu("&Debug")
            debugMenu.addAction("Hard &Refresh", self.refresh, QKeySequence(Qt.CTRL + Qt.Key_F5))
            debugMenu.addAction("Dump Graph...", self.debug_saveGraphDump)
            debugMenu.addAction("Load Graph...", self.debug_loadGraphDump)

        helpMenu = menubar.addMenu("&Help")
        helpMenu.addAction(F"About {settings.PROGRAM_NAME}", self.about)
        helpMenu.addAction("About Qt", lambda: QMessageBox.aboutQt(self))

        self.fillRecentMenu()

        # couldn't get menubar.cornerWidget to work, otherwise we could've used that
        if not settings.prefs.tabs_mergeWithMenubar:  # traditional menu bar
            self.setMenuBar(menubar)
        else:  # extended menu bar
            menuContainer = QWidget()
            menuContainer.setLayout(QHBoxLayout())
            menuContainer.layout().setSpacing(0)
            menuContainer.layout().setContentsMargins(0, 0, 0, 0)
            menuContainer.layout().addWidget(menubar)
            menuContainer.layout().addSpacing(8)
            menuContainer.layout().addWidget(self.tabs.tabs, 1)
            self.tabs.tabs.setMaximumHeight(menubar.height())
            self.setMenuWidget(menuContainer)
            menubar.adjustSize()

    def openSettings(self):
        dlg = PrefsDialog(self)
        rc = dlg.exec_()
        dlg.deleteLater()  # avoid leaking dialog (can't use WA_DeleteOnClose because we needed to retrieve the message)
        if rc != PrefsDialog.Accepted:
            return
        if not dlg.prefDiff:  # No changes were made to the prefs
            return
        # Apply changes from prefDiff to the actual prefs
        for k in dlg.prefDiff:
            settings.prefs.__dict__[k] = dlg.prefDiff[k]
        # Write prefs to disk
        settings.prefs.write()
        QMessageBox.warning(
            self,
            "Apply Settings",
            F"Some changes may require restarting {settings.PROGRAM_NAME} to take effect.")

    def about(self):
        import sys
        about_text = F"""\
        <h2>{settings.PROGRAM_NAME} {settings.VERSION}</h2>
        <p>
        The no-frills git GUI for Linux
        </p>
        <p><small>
        {git.Git().version()}<br>
        Python {sys.version}<br>
        GitPython {git.__version__}<br>
        Qt {qtVersion}<br>
        PySide {qtBindingVersion}
        </small></p>
        """
        QMessageBox.about(self, F"About {settings.PROGRAM_NAME}", about_text)

    def fillRecentMenu(self):
        self.recentMenu.clear()
        for historic in reversed(settings.history.history):
            self.recentMenu.addAction(
                F"{settings.history.getRepoNickname(historic)} [{compactSystemPath(historic)}]",
                lambda h=historic: self.openRepo(h))

    def currentRepoWidget(self) -> RepoWidget:
        return self.tabs.currentWidget()

    def onTabChange(self, i):
        #if self.previousTabIndex >= 0:
        #    pw = self.tabs.widget(previous...) # also save splitter state after close
        #    self.splitterStates = self
        if i < 0:
            self.setWindowTitle(settings.PROGRAM_NAME)
            return

        w = self.currentRepoWidget()
        w.restoreSplitterStates()

        # If we don't have a RepoState, then the tab is lazy-loaded.
        # We need to load it now.
        if not w.state:
            # Disable tabs widget while we're loading the repo to prevent tabs
            # from accidentally being dragged while the UI is locking up
            with DisableWidgetContext(self.tabs):
                # Load repo
                success = self._loadRepo(w, w.workingTreeDir)
                if not success:
                    return

        shortname = w.state.shortName
        repo = w.state.repo
        inBrackets = ""
        if repo.head.is_detached:
            inBrackets = F"detached HEAD @ {repo.head.commit.hexsha[:settings.prefs.shortHashChars]}"
        else:
            inBrackets = str(repo.active_branch)
        self.setWindowTitle(F"{shortname} [{inBrackets}] — {settings.PROGRAM_NAME}")

    def onTabContextMenu(self, globalPoint: QPoint, i: int):
        if i < 0:  # Right mouse button released outside tabs
            return
        rw: RepoWidget = self.tabs.stacked.widget(i)
        menu = QMenu()
        menu.addAction("Close Tab", lambda: self.closeTab(i))
        menu.addAction("Close Other Tabs", lambda: self.closeOtherTabs(i))
        menu.addSeparator()
        menu.addAction("Open Repo Folder", lambda: self.openRepoFolder(rw))
        menu.addAction("Rename", rw.renameRepo)
        menu.addSeparator()
        if rw.state:
            menu.addAction("Unload", lambda: self.unloadTab(i))
        else:
            menu.addAction("Load", lambda: self.loadTab(i))
        #self.tabs.tabs.
        menu.exec_(globalPoint)

    def _loadRepo(self, rw: RepoWidget, path: str):
        assert rw

        shortname = settings.history.getRepoNickname(path)
        progress = QProgressDialog("Opening repository.", "Abort", 0, 0, self)
        progress.setAttribute(Qt.WA_DeleteOnClose)  # avoid leaking the dialog
        progress.setWindowModality(Qt.WindowModal)
        progress.setWindowTitle(shortname)
        progress.setWindowFlags(Qt.Dialog | Qt.Popup)
        progress.setMinimumWidth(2 * progress.fontMetrics().horizontalAdvance("000,000,000 commits loaded."))
        QCoreApplication.processEvents()
        progress.show()
        QCoreApplication.processEvents()
        #import time; time.sleep(3)

        try:
            newState = RepoState(path)
            #orderedMetadata = newState.loadCommitList_Sequential(progress)
            orderedMetadata = newState.loadCommitList(progress)

            rw.state = newState

            progress.setLabelText(F"Filling model.")
            progress.setMaximum(0)
            progress.setValue(0)

            rw.graphView.fill(orderedMetadata)
            rw.sidebar.fill(newState.repo)

            self.refreshTabText(rw)
        except BaseException as e:
            progress.close()

            known = path in settings.history.history

            message = F"Couldn't open \"{path}\""

            if isinstance(e, git.exc.InvalidGitRepositoryError):
                message += " because it is not a git repository."
            elif isinstance(e, git.exc.NoSuchPathError):
                message += " because this path does not exist."
            else:
                message += " because an exception was thrown."
                excMessageBox(e, message=message)
                return False

            qmb = QMessageBox(self)
            qmb.setIcon(QMessageBox.Critical)
            qmb.setWindowTitle("Reopen repository" if known else "Open repository")
            ok = qmb.addButton("OK", QMessageBox.RejectRole)
            nukeButton = None
            if known:
                nukeButton = qmb.addButton("Remove from recents", QMessageBox.DestructiveRole)
            qmb.setDefaultButton(ok)
            qmb.setText(message)
            qmb.exec_()
            if qmb.clickedButton() == nukeButton:
                settings.history.removeRepo(path)
            return False

        progress.close()
        return True

    def openRepo(self, repoPath, foreground=True):
        newRW = RepoWidget(self, self.sharedSplitterStates)

        if foreground:
            if not self._loadRepo(newRW, repoPath):
                newRW.destroy()
                return  # don't create the tab if opening the repo failed
        else:
            newRW.pathPending = repoPath

        tabIndex = self.tabs.addTab(newRW, newRW.getTitle(), compactSystemPath(repoPath))

        if foreground:
            self.tabs.setCurrentIndex(tabIndex)

        newRW.nameChange.connect(lambda: self.refreshTabText(newRW))

        settings.history.addRepo(repoPath)
        self.fillRecentMenu()

    def quickRefresh(self):
        rw = self.currentRepoWidget()
        rw.quickRefresh()

    def refresh(self):
        rw = self.currentRepoWidget()
        self._loadRepo(rw, rw.workingTreeDir)

    def openRepoFolder(self, rw: RepoWidget = None):
        if not rw:
            rw = self.currentRepoWidget()
        showInFolder(rw.workingTreeDir)

    def openDialog(self):
        path = settings.history.openFileDialogLastPath
        path = QFileDialog.getExistingDirectory(self, "Open repository", path)
        if path:
            settings.history.openFileDialogLastPath = path
            settings.history.write()
            self.openRepo(path)

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
        self._loadRepo(rw, rw.workingTreeDir)

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

    def selectUncommittedChanges(self):
        self.currentRepoWidget().graphView.selectUncommittedChanges()

    def tryLoadSession(self):
        session = settings.Session()
        if not session.load():
            return

        self.sharedSplitterStates = {k: settings.decodeBinary(session.splitterStates[k]) for k in session.splitterStates}
        self.restoreGeometry(settings.decodeBinary(session.windowGeometry))
        self.show()

        # Normally, changing the current tab will load the corresponding repo in the background.
        # But we don't want to load every repo as we're creating tabs, so temporarily disconnect the signal.
        self.tabs.stacked.currentChanged.disconnect(self.onTabChange)

        # Lazy-loading: prepare all tabs, but don't load the repos (foreground=False).
        for r in session.tabs:
            try:
                self.openRepo(r, foreground=False)
            except BaseException as exc:
                excMessageBox(exc, title="Restore Session")

        # Set the current tab.
        self.tabs.setCurrentIndex(session.activeTabIndex)

        # Load the current tab's repo. Catch exceptions so __main__ doesn't get aborted.
        try:
            self.onTabChange(session.activeTabIndex)
        except BaseException as exc:
            excMessageBox(exc, title="Restore Session")

        # Now reconnect the signal.
        self.tabs.stacked.currentChanged.connect(self.onTabChange)

    def saveSession(self):
        session = settings.Session()
        session.windowGeometry = settings.encodeBinary(self.saveGeometry())
        if self.currentRepoWidget():
            session.splitterStates = {s.objectName(): settings.encodeBinary(s.saveState()) for s in self.currentRepoWidget().splittersToSave}
        else:
            session.splitterStates = {}
        session.tabs = [self.tabs.widget(i).workingTreeDir for i in range(self.tabs.count())]
        session.activeTabIndex = self.tabs.currentIndex()
        session.write()

    def closeEvent(self, e):
        self.saveSession()
        e.accept()

    def debug_loadGraphDump(self):
        rw = self.currentRepoWidget()
        path, _ = QFileDialog.getOpenFileName(self, "Load graph dump")
        if not path:
            return

        progress = QProgressDialog("Load graph dump", "Abort", 0, 0, self)
        progress.setAttribute(Qt.WA_DeleteOnClose)  # avoid leaking the dialog
        progress.setWindowModality(Qt.WindowModal)
        progress.setWindowTitle(rw.state.shortName)
        progress.setWindowFlags(Qt.Dialog | Qt.Popup)
        QCoreApplication.processEvents()
        progress.setMaximum(5)
        progress.show()
        QCoreApplication.processEvents()

        progress.setValue(0)
        with open(path, 'rb') as f:
            raw = f.read()
        progress.setValue(1)
        unpacked = zlib.decompress(raw)
        progress.setValue(2)
        dump = pickle.loads(unpacked)
        progress.setValue(3)
        orderedMetadata = rw.state.loadCommitDump(dump)
        progress.setValue(4)
        rw.graphView.fill(orderedMetadata)

        progress.close()

    def debug_saveGraphDump(self):
        rw = self.currentRepoWidget()
        path, _ = QFileDialog.getSaveFileName(self, "Save graph dump", rw.state.shortName + ".gfgraphdump")
        if not path:
            return
        print(path)

        progress = QProgressDialog("Save graph dump", "Abort", 0, 0, self)
        progress.setAttribute(Qt.WA_DeleteOnClose)  # avoid leaking the dialog
        progress.setWindowModality(Qt.WindowModal)
        progress.setWindowTitle(rw.state.shortName)
        progress.setWindowFlags(Qt.Dialog | Qt.Popup)
        QCoreApplication.processEvents()
        progress.setMaximum(4)
        progress.show()
        QCoreApplication.processEvents()

        progress.setValue(0)
        dump = rw.state.makeCommitDump()
        progress.setValue(1)
        raw = pickle.dumps(dump)
        progress.setValue(2)
        compressed = zlib.compress(raw)
        progress.setValue(3)
        with open(path, 'wb') as f:
            f.write(compressed)

        progress.setValue(4)
        progress.close()
