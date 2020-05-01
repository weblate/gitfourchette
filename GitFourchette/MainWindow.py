import git
from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *
import globals
import os

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
        self.createFileMenu(fileMenu)

        helpMenu = menubar.addMenu("&Help")
        helpMenu.addAction(F"About {globals.PROGRAM_NAME}", lambda: QMessageBox.about(
            self, F"About {globals.PROGRAM_NAME}", globals.PROGRAM_ABOUT))
        helpMenu.addAction("About Qt", lambda: QMessageBox.aboutQt(self))

        self.graphView = GraphView.GraphView(self)
        self.treeView = TreeView.TreeView(self)
        self.diffView = DiffView.DiffView(self)

        vbox = QVBoxLayout()
        vbox.setSpacing(0)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.addWidget(menubar)
        vsplitter = QSplitter(Qt.Vertical)
        vbox.addWidget(vsplitter)
        vsplitter.addWidget(self.graphView)
        hsplitter = QSplitter(Qt.Horizontal)
        vsplitter.addWidget(hsplitter)
        hsplitter.addWidget(self.treeView)
        hsplitter.addWidget(self.diffView)
        vsplitter.setSizes([100, 150])
        hsplitter.setSizes([100, 300])
        self.setWindowTitle(globals.PROGRAM_NAME)

        self.setWindowIcon(QIcon("icons/logo.svg"))
        self.setLayout(vbox)

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
    def setRepo(self, gitRepoDirPath):
        self.ready = False
        oldState = self.state
        try:
            self.state = None # for isReady
            print("Loading state...")
            self.state = RepoState(gitRepoDirPath)
            globals.addRepoToHistory(gitRepoDirPath)
            print("OK. " + str(self.state.repo))
            print(self.state.repo.active_branch)
            print("Fill GV...")
            self.graphView.fill(self.state.repo)
            print("Done.")
            shortname = os.path.basename(self.state.repo.working_tree_dir)
            #shortpath = self.state.repo.working_tree_dir
            #from pathlib import Path
            #if shortpath.startswith(str(Path.home())):
            #    shortpath = "~" + shortpath[len(str(Path.home())):]
            self.setWindowTitle(F"{shortname} [{self.state.repo.active_branch}] — {globals.PROGRAM_NAME}")
        except git.exc.InvalidGitRepositoryError as e:
            self.state = oldState
            print(e)
            QMessageBox.warning(
                self,
                "Invalid repository",
                F"This directory does not appear to be a valid git repository:\n{gitRepoDirPath}")
        except BaseException as e:
            self.state = oldState
            print(e)
            QMessageBox.critical(
                self,
                "Error",
                "Exception thrown while opening repository:\n\n" + str(e))
        self.ready = True

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

        globals.appSettings.setValue("repos", [self.state.dir, "test"])

        e.accept()
