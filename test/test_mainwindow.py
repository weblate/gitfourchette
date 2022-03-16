from . import reposcenario
from .fixtures import *
from .util import *
from gitfourchette.widgets.clonedialog import CloneDialog
import os
import pygit2


def testDropDirectoryOntoMainWindowOpensRepository(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    wdUrl = QUrl.fromLocalFile(wd)
    mime = QMimeData()
    mime.setUrls([wdUrl])

    assert mainWindow.tabs.count() == 0
    assert mainWindow.currentRepoWidget() is None

    pos = QPoint(mainWindow.width()//2, mainWindow.height()//2)
    dropEvent = QDropEvent(pos, Qt.MoveAction, mime, Qt.LeftButton, Qt.NoModifier)
    dropEvent.acceptProposedAction()
    mainWindow.dropEvent(dropEvent)

    assert mainWindow.tabs.count() == 1
    assert mainWindow.currentRepoWidget().repo.workdir == wd


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


def testOpenSameRepoTwice(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)

    rw1 = mainWindow.openRepo(wd)
    assert mainWindow.tabs.count() == 1
    assert mainWindow.currentRepoWidget() == rw1

    rw2 = mainWindow.openRepo(wd)  # exact same workdir path
    assert mainWindow.tabs.count() == 1  # don't create a new tab
    assert mainWindow.currentRepoWidget() == rw2

    rw3 = mainWindow.openRepo(wd + os.path.sep)  # trailing slash
    assert mainWindow.tabs.count() == 1  # don't create a new tab
    assert mainWindow.currentRepoWidget() == rw3

    rw4 = mainWindow.openRepo(os.path.join(wd, "master.txt"))  # some file within workdir
    assert mainWindow.tabs.count() == 1  # don't create a new tab
    assert mainWindow.currentRepoWidget() == rw4
