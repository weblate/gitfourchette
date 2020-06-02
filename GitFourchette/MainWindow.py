from typing import List

import git
from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *
import settings
import os
import traceback
from RepoState import RepoState
from RepoWidget import RepoWidget
from util import compactSystemPath, showInFolder


class Session:
    openTabs: List[str]
    activeTab: int
    geometry: QRect


class MainWindow(QMainWindow):
    tabs: QTabWidget
    previousTabIndex: int

    def __init__(self):
        super().__init__()

        self.sharedSplitterStates = {}

        self.setWindowTitle(settings.PROGRAM_NAME)
        self.setWindowIcon(QIcon("icons/gf.png"))
        self.resize(QSize(800, 600))
        self.move(QPoint(50, 50))
        #self.resize(settings.appSettings.value("MainWindow/size", QSize(800, 600)))
        #self.move(settings.appSettings.value("MainWindow/position", QPoint(50, 50)))

        self.previousTabIndex = -1
        self.tabs = QTabWidget()
        #self.tabs.setTabBarAutoHide(True)
        self.tabs.setMovable(True)

        self.tabs.currentChanged.connect(self.onTabChange)

        self.setCentralWidget(self.tabs)

        self.makeMenu()

    def makeMenu(self):
        menubar = QMenuBar()

        fileMenu = menubar.addMenu("&File")
        fileMenu.addAction("&Open", self.openDialog, QKeySequence.Open)
        self.recentMenu = fileMenu.addMenu("Open &Recent")
        fileMenu.addAction("&Close Tab", self.closeTab, QKeySequence.Close)
        fileMenu.addSeparator()
        fileMenu.addAction("&Quit", self.close, QKeySequence.Quit)

        repoMenu = menubar.addMenu("&Repo")
        repoMenu.addAction("&Refresh", self.refresh, QKeySequence.Refresh)
        repoMenu.addAction("Open Repo Folder", self.openRepoFolder)
        repoMenu.addSeparator()
        repoMenu.addAction("Push", lambda: self.currentRepoWidget().push())
        repoMenu.addAction("Rename...", lambda: self.currentRepoWidget().renameRepo())

        helpMenu = menubar.addMenu("&Help")
        helpMenu.addAction(F"About {settings.PROGRAM_NAME}", self.about)
        helpMenu.addAction("About Qt", lambda: QMessageBox.aboutQt(self))
        helpMenu.addSeparator()
        helpMenu.addAction("Memory", self.memInfo)

        self.fillRecentMenu()
        self.setMenuBar(menubar)

    def about(self):
        import sys, PySide2
        about_text = F"""\
        <h2>{settings.PROGRAM_NAME} {settings.VERSION}</h2>
        <p><small>
        {git.Git().version()}<br>
        Python {sys.version}<br>
        GitPython {git.__version__}<br>
        Qt {PySide2.QtCore.__version__}<br>
        PySide2 {PySide2.__version__}
        </small></p>
        <p>
        This is my git frontend.<br>There are many like it but this one is mine.
        </p>
        """
        QMessageBox.about(self, F"About {settings.PROGRAM_NAME}", about_text)

    def memInfo(self):
        import psutil, gc
        gc.collect()
        QMessageBox.information(self, F"Memory usage", F"{psutil.Process(os.getpid()).memory_info().rss:,}")

    def fillRecentMenu(self):
        self.recentMenu.clear()
        for historic in settings.history.history:
            self.recentMenu.addAction(
                F"{settings.history.getRepoNickname(historic)} [{compactSystemPath(historic)}]",
                lambda h=historic: self.openRepo(h))

    def currentRepoWidget(self) -> RepoWidget:
        return self.tabs.widget(self.tabs.currentIndex())

    def onTabChange(self, i):
        #if self.previousTabIndex >= 0:
        #    pw = self.tabs.widget(previous...) # also save splitter state after close
        #    self.splitterStates = self
        if i < 0:
            self.setWindowTitle(settings.PROGRAM_NAME)
            return
        w = self.currentRepoWidget()
        w.restoreSplitterStates()
        shortname = settings.history.getRepoNickname(w.state.repo.working_tree_dir)
        self.setWindowTitle(F"{shortname} [{w.state.repo.active_branch}] — {settings.PROGRAM_NAME}")

    def _loadRepo(self, rw: RepoWidget, path: str):
        assert rw

        shortname = settings.history.getRepoNickname(path)
        progress = QProgressDialog("Opening repository...", "Abort", 0, 0, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setWindowTitle(shortname)
        progress.setWindowFlags(Qt.Dialog | Qt.Popup)
        progress.setMinimumWidth(2 * progress.fontMetrics().width("000,000,000 commits loaded."))
        QCoreApplication.processEvents()
        progress.show()
        QCoreApplication.processEvents()
        #import time; time.sleep(3)

        try:
            newState = RepoState(path)
        except BaseException as e:
            progress.close()
            traceback.print_exc()
            if isinstance(e, git.exc.InvalidGitRepositoryError):
                QMessageBox.warning(self, "Invalid repository", F"Couldn't open \"{path}\" because it is not a git repository.")
            else:
                QMessageBox.critical(self, "Error", F"Couldn't open \"{path}\" because an exception was thrown.\n{e.__class__.__name__}: {e}.\nCheck stderr for details.")
            return False

        rw.state = newState
        rw.graphView.fill(progress)
        progress.close()
        return True

    def openRepo(self, repoPath):
        newRW = RepoWidget(self, self.sharedSplitterStates)

        if not self._loadRepo(newRW, repoPath):
            newRW.destroy()

        tabIndex = self.tabs.addTab(newRW, settings.history.getRepoNickname(repoPath))
        self.tabs.setCurrentIndex(tabIndex)
        
        settings.history.addRepo(repoPath)
        self.fillRecentMenu()

    def refresh(self):
        rw = self.currentRepoWidget()
        self._loadRepo(rw, rw.state.repo.working_tree_dir)

    def openRepoFolder(self):
        rw = self.currentRepoWidget()
        showInFolder(rw.state.repo.working_tree_dir)

    def openDialog(self):
        path = settings.history.openFileDialogLastPath
        path = QFileDialog.getExistingDirectory(self, "Open repository", path)
        if path:
            settings.history.openFileDialogLastPath = path
            settings.history.write()
            self.openRepo(path)

    def closeTab(self):
        self.currentRepoWidget().cleanup()
        self.tabs.removeTab(self.tabs.currentIndex())

    def tryLoadSession(self):
        session = settings.Session()
        if not session.load():
            return
        self.sharedSplitterStates = {k:settings.decodeBinary(session.splitterStates[k]) for k in session.splitterStates}
        self.restoreGeometry(settings.decodeBinary(session.windowGeometry))
        self.show()
        for r in session.tabs:
            self.openRepo(r)
        self.tabs.setCurrentIndex(session.activeTabIndex)

    def saveSession(self):
        session = settings.Session()
        session.windowGeometry = settings.encodeBinary(self.saveGeometry())
        session.splitterStates = {s.objectName(): settings.encodeBinary(s.saveState()) for s in self.currentRepoWidget().splittersToSave}
        session.tabs = [self.tabs.widget(i).state.repo.working_tree_dir for i in range(self.tabs.count())]
        session.activeTabIndex = self.tabs.currentIndex()
        session.write()

    def closeEvent(self, e):
        self.saveSession()
        e.accept()
