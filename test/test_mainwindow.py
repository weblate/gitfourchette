from . import reposcenario
from .fixtures import *
from .util import *
from gitfourchette.widgets.clonedialog import CloneDialog
import os
import pygit2


@withRepo("TestGitRepository")
@withPrep(None)
def testDropDirectoryOntoMainWindowOpensRepository(qtbot, workDir, mainWindow):
    assert mainWindow.tabs.count() == 0
    assert mainWindow.currentRepoWidget() is None

    wdUrl = QUrl.fromLocalFile(workDir)

    mime = QMimeData()
    mime.setUrls([wdUrl])

    pos = QPoint(mainWindow.width()//2, mainWindow.height()//2)
    dropEvent = QDropEvent(pos, Qt.MoveAction, mime, Qt.LeftButton, Qt.NoModifier)
    dropEvent.acceptProposedAction()
    mainWindow.dropEvent(dropEvent)

    assert mainWindow.tabs.count() == 1
    assert mainWindow.currentRepoWidget().repo.workdir == workDir


def testDropUrlOntoMainWindowBringsUpCloneDialog(qtbot, mainWindow):
    assert mainWindow.tabs.count() == 0
    assert mainWindow.currentRepoWidget() is None

    wdUrl = QUrl("https://github.com/jorio/bugdom")

    mime = QMimeData()
    mime.setUrls([wdUrl])

    pos = QPoint(mainWindow.width()//2, mainWindow.height()//2)
    dropEvent = QDropEvent(pos, Qt.MoveAction, mime, Qt.LeftButton, Qt.NoModifier)
    dropEvent.acceptProposedAction()
    mainWindow.dropEvent(dropEvent)

    cloneDialog: CloneDialog = findQDialog(mainWindow, "clone")
    assert cloneDialog is not None
    assert cloneDialog.url == wdUrl.toString()

    cloneDialog.reject()


@withRepo("TestGitRepository")
@withPrep(None)
def testOpenSameRepoTwice(qtbot, workDir, mainWindow):
    print(workDir)

    rw1 = mainWindow.openRepo(workDir)
    assert mainWindow.tabs.count() == 1
    assert mainWindow.currentRepoWidget() == rw1

    rw2 = mainWindow.openRepo(workDir)
    assert mainWindow.tabs.count() == 1  # don't create a new tab
    assert mainWindow.currentRepoWidget() == rw2

    rw3 = mainWindow.openRepo(workDir + os.path.sep)
    assert mainWindow.tabs.count() == 1  # don't create a new tab
    assert mainWindow.currentRepoWidget() == rw3
