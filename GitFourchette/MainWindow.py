import git
from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *
import globals
import os
import traceback
from RepoState import RepoState
from RepoWidget import RepoWidget
from util import compactPath


class MainWindow(QMainWindow):
    tabs: QTabWidget

    def __init__(self):
        super().__init__()

        self.setWindowTitle(globals.PROGRAM_NAME)
        self.setWindowIcon(QIcon("icons/gf.png"))
        self.resize(globals.appSettings.value("MainWindow/size", QSize(800, 600)))
        self.move(globals.appSettings.value("MainWindow/position", QPoint(50, 50)))

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
        fileMenu.addSeparator()
        fileMenu.addAction("&Quit", self.close, QKeySequence.Quit)

        repoMenu = menubar.addMenu("&Repo")
        repoMenu.addAction("Push", lambda: self.repoWidget.push())
        repoMenu.addAction("Rename...", lambda: self.repoWidget.renameRepo())

        helpMenu = menubar.addMenu("&Help")
        helpMenu.addAction(F"About {globals.PROGRAM_NAME}", self.about)
        helpMenu.addAction("About Qt", lambda: QMessageBox.aboutQt(self))
        helpMenu.addSeparator()
        helpMenu.addAction("Memory", self.memInfo)

        self.fillRecentMenu()
        self.setMenuBar(menubar)

    def about(self):
        import sys, PySide2
        about_text = F"""\
        <h2>{globals.PROGRAM_NAME} {globals.VERSION}</h2>
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
        QMessageBox.about(self, F"About {globals.PROGRAM_NAME}", about_text)

    def memInfo(self):
        import psutil, gc
        gc.collect()
        QMessageBox.information(self, F"Memory usage", F"{psutil.Process(os.getpid()).memory_info().rss:,}")

    def fillRecentMenu(self):
        self.recentMenu.clear()
        for historic in globals.getRepoHistory():
            self.recentMenu.addAction(
                F"{globals.getRepoNickname(historic)} [{compactPath(historic)}]",
                lambda h=historic: self.openRepo(h))

    def onTabChange(self, i):
        if i < 0:
            self.setWindowTitle(globals.PROGRAM_NAME)
            return
        w: RepoWidget = self.tabs.widget(self.tabs.currentIndex())
        shortname = globals.getRepoNickname(w.state.repo.working_tree_dir)
        self.setWindowTitle(F"{shortname} [{w.state.repo.active_branch}] — {globals.PROGRAM_NAME}")

    def openRepo(self, gitRepoDirPath):
        shortname = globals.getRepoNickname(gitRepoDirPath)
        progress = QProgressDialog("Opening repository...", "Abort", 0, 0, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setWindowTitle(shortname)
        progress.setWindowFlags(Qt.Dialog | Qt.Popup)
        progress.setMinimumWidth(2 * progress.fontMetrics().width("000,000,000 commits loaded."))
        QCoreApplication.processEvents()
        progress.show()
        QCoreApplication.processEvents()
        #import time; time.sleep(3)

        newRW = RepoWidget(self)
        try:
            newRW.state = RepoState(gitRepoDirPath)
            globals.addRepoToHistory(gitRepoDirPath)
            self.fillRecentMenu()
            newRW.graphView.fill(progress)
            newIndex = self.tabs.addTab(newRW, shortname)
            self.tabs.setCurrentIndex(newIndex)
        except BaseException as e:
            newRW.destroy()
            progress.close()
            traceback.print_exc()
            if isinstance(e, git.exc.InvalidGitRepositoryError):
                QMessageBox.warning(self, "Invalid repository", F"Couldn't open \"{gitRepoDirPath}\" because it is not a git repository.")
            else:
                QMessageBox.critical(self, "Error", F"Couldn't open \"{gitRepoDirPath}\" because an exception was thrown.\n{e.__class__.__name__}: {e}.\nCheck stderr for details.")
            return
        finally:
            progress.close()

    def openDialog(self):
        path = QFileDialog.getExistingDirectory(self, "Open repository", globals.appSettings.value(globals.SK_LAST_OPEN, "", type=str))
        if path:
            globals.appSettings.setValue(globals.SK_LAST_OPEN, path)
            self.openRepo(path)

    def closeEvent(self, e):
        # Write window size and position to config file
        globals.appSettings.setValue("MainWindow/size", self.size())
        globals.appSettings.setValue("MainWindow/position", self.pos())
        self.repoWidget.saveSplitterStates()
        e.accept()
