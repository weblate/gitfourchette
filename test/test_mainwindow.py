import os

import pytest

from gitfourchette.forms.clonedialog import CloneDialog
from gitfourchette.mainwindow import NoRepoWidgetError
from .util import *


def testDropDirectoryOntoMainWindowOpensRepository(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    wdUrl = QUrl.fromLocalFile(wd)
    mime = QMimeData()
    mime.setUrls([wdUrl])

    assert mainWindow.tabs.count() == 0
    with pytest.raises(NoRepoWidgetError):
        mainWindow.currentRepoWidget()

    pos = QPointF(mainWindow.width()//2, mainWindow.height()//2)
    dropEvent = QDropEvent(pos, Qt.DropAction.MoveAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    dropEvent.acceptProposedAction()
    mainWindow.dropEvent(dropEvent)

    assert mainWindow.tabs.count() == 1
    assert os.path.normpath(mainWindow.currentRepoWidget().repo.workdir) == os.path.normpath(wd)


def testDropUrlOntoMainWindowBringsUpCloneDialog(mainWindow):
    assert mainWindow.tabs.count() == 0
    with pytest.raises(NoRepoWidgetError):
        mainWindow.currentRepoWidget()

    wdUrl = QUrl("https://github.com/jorio/bugdom")

    mime = QMimeData()
    mime.setUrls([wdUrl])

    pos = QPointF(mainWindow.width()//2, mainWindow.height()//2)
    dropEvent = QDropEvent(pos, Qt.DropAction.MoveAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    dropEvent.acceptProposedAction()
    mainWindow.dropEvent(dropEvent)

    cloneDialog: CloneDialog = findQDialog(mainWindow, "clone")
    assert cloneDialog is not None
    assert cloneDialog.url == wdUrl.toString()

    cloneDialog.reject()


def testOpenSameRepoTwice(tempDir, mainWindow):
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

    rw4 = mainWindow.openRepo(os.path.join(wd, "master.txt"), exactMatch=False)  # some file within workdir
    assert mainWindow.tabs.count() == 1  # don't create a new tab
    assert mainWindow.currentRepoWidget() == rw4
