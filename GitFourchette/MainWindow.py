import git
from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *
import globals
import os
import traceback
import psutil
import gc

from pathlib import Path


def compactPath(path: str) -> str:
    home = str(Path.home())
    if path.startswith(str(home)):
        path = "~" + path[len(home):]
    return path


class RepoState:
    def __init__(self, dir):
        self.dir = os.path.abspath(dir)
        self.repo = git.Repo(dir)
        self.index = self.repo.index


class MainWindow(QWidget):
    def __init__(self):
        super(__class__, self).__init__()

        import DiffView, GraphView, TreeView

        self.ready = False
        self.state = None

        self.resize(globals.appSettings.value("MainWindow/size", QSize(800, 600)))
        self.move(globals.appSettings.value("MainWindow/position", QPoint(50, 50)))

        menubar = QMenuBar()
        fileMenu = menubar.addMenu("&File")
        repoMenu = menubar.addMenu("&Repo")
        self.createFileMenu(fileMenu)
        self.createRepoMenu(repoMenu)

        helpMenu = menubar.addMenu("&Help")
        helpMenu.addAction("GC", lambda: gc.collect())
        helpMenu.addAction("Memory", lambda: QMessageBox.about(
            self, F"Memory usage", F"Memory: {psutil.Process(os.getpid()).memory_info().rss:,}"
        ))
        helpMenu.addAction(F"About {globals.PROGRAM_NAME}", lambda: QMessageBox.about(
            self, F"About {globals.PROGRAM_NAME}", globals.PROGRAM_ABOUT))
        helpMenu.addAction("About Qt", lambda: QMessageBox.aboutQt(self))

        self.graphView = GraphView.GraphView(self)
        self.filesStack = QStackedWidget()
        self.diffView = DiffView.DiffView(self)
        self.changedFilesView = TreeView.TreeView(self)
        self.unstagedFilesView = TreeView.TreeView(self)
        self.stagedFilesView = TreeView.TreeView(self)

        windowVBox = QVBoxLayout()
        windowVBox.setSpacing(0)
        windowVBox.setContentsMargins(0, 0, 0, 0)
        windowVBox.addWidget(menubar)

        stageSplitter = QSplitter(Qt.Vertical)
        stageSplitter.setHandleWidth(globals.splitterHandleWidth)
        stageSplitter.addWidget(self.unstagedFilesView)
        stageSplitter.addWidget(self.stagedFilesView)

        self.filesStack.addWidget(self.changedFilesView)
        self.filesStack.addWidget(stageSplitter)
        self.filesStack.setCurrentIndex(0)

        bottomSplitter = QSplitter(Qt.Horizontal)
        bottomSplitter.setHandleWidth(globals.splitterHandleWidth)
        bottomSplitter.addWidget(self.filesStack)
        bottomSplitter.addWidget(self.diffView)

        bottomSplitter.setSizes([100, 300])

        mainSplitter = QSplitter(Qt.Vertical)
        mainSplitter.setHandleWidth(globals.splitterHandleWidth)
        mainSplitter.addWidget(self.graphView)
        mainSplitter.addWidget(bottomSplitter)
        mainSplitter.setSizes([100, 150])

        windowVBox.addWidget(mainSplitter)

        self.setWindowTitle(globals.PROGRAM_NAME)

        self.setWindowIcon(QIcon("icons/logo.svg"))
        self.setLayout(windowVBox)

        self.ready = True

    def createFileMenu(self, m: QMenu):
        m.clear()

        m.addAction(
            "&Open",
            lambda: self.open(),
            QKeySequence.Open)

        recentMenu = m.addMenu("Open &Recent")
        for historic in globals.getRepoHistory():
            recentMenu.addAction(
                F"{globals.getRepoNickname(historic)} [{compactPath(historic)}]",
                lambda h=historic: self.setRepo(h))

        m.addSeparator()

        m.addAction(
            "&Quit",
            lambda: self.close(),
            QKeySequence.Quit)

    def createRepoMenu(self, m: QMenu):
        m.clear()
        m.addAction("Rename...", lambda: self.renameRepo())

    def renameRepo(self):
        text, ok = QInputDialog().getText(
            self,
            "Rename repo", "Enter new nickname for repo:",
            QLineEdit.Normal,
            globals.getRepoNickname(self.state.dir)
        )
        if ok:
            globals.setRepoNickname(self.state.dir, text)

    def unready(self):
        return LockContext(self)

    def setRepo(self, gitRepoDirPath):
        with self.unready():
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

            oldState = self.state
            self.state = None  # for isReady
            try:
                self.state = RepoState(gitRepoDirPath)
                globals.addRepoToHistory(gitRepoDirPath)
                self.graphView.fill(self.state.repo, progress)
                self.setWindowTitle(F"{shortname} [{self.state.repo.active_branch}] — {globals.PROGRAM_NAME}")
                progress.close()
            except git.exc.InvalidGitRepositoryError as e:
                progress.close()
                self.state = oldState
                print(traceback.format_exc())
                QMessageBox.warning(
                    self,
                    "Invalid repository",
                    F"This directory does not appear to be a valid git repository:\n{gitRepoDirPath}")
            except BaseException as e:
                progress.close()
                self.state = oldState
                print(traceback.format_exc())
                QMessageBox.critical(
                    self,
                    "Error",
                    "Exception thrown while opening repository:\n\n" + str(e))

    def isReady(self):
        return self.ready and self.state != None

    def open(self):
        path = QFileDialog.getExistingDirectory(self, "Open repository", globals.appSettings.value(globals.SK_LAST_OPEN, "", type=str))
        if path:
            globals.appSettings.setValue(globals.SK_LAST_OPEN, path)
            self.setRepo(path)

    def closeEvent(self, e):
        # Write window size and position to config file
        globals.appSettings.setValue("MainWindow/size", self.size())
        globals.appSettings.setValue("MainWindow/position", self.pos())
        e.accept()


class LockContext(object):
    w: MainWindow

    def __init__(self, w):
        self.w = w

    def __enter__(self):
        self.w.ready = False

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.w.ready = True
