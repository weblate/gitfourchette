from helpers.qttest_imports import *
from helpers import reposcenario, testutil
from helpers.fixtures import *
from widgets.clonedialog import CloneDialog
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

    cloneDialog: CloneDialog = testutil.findQDialog(mainWindow, "clone")
    assert cloneDialog is not None
    assert cloneDialog.url == wdUrl.toString()

    cloneDialog.reject()

