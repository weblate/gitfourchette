from . import reposcenario
from .fixtures import *
from .util import *
from gitfourchette.widgets.repowidget import RepoWidget
from gitfourchette.widgets.remotedialog import RemoteDialog
from gitfourchette.widgets.sidebar import EItem
from gitfourchette import porcelain
import re


def testNewRemote(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    repo = rw.repo

    # Ensure we're starting with the expected settings
    assert len(repo.remotes) == 1
    assert repo.remotes[0].name == "origin"

    menu = rw.sidebar.generateMenuForEntry(EItem.RemotesHeader)

    findMenuAction(menu, "add remote").trigger()

    q: RemoteDialog = findQDialog(rw, "add remote")
    q.ui.nameEdit.setText("otherremote")
    q.ui.urlEdit.setText("https://127.0.0.1/example-repo.git")
    q.accept()

    assert len(repo.remotes) == 2
    assert repo.remotes[1].name == "otherremote"
    assert repo.remotes[1].url == "https://127.0.0.1/example-repo.git"


def testEditRemote(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    repo = rw.repo

    # Ensure we're starting with the expected settings
    assert len(repo.remotes) == 1
    assert repo.remotes[0].name == "origin"

    menu = rw.sidebar.generateMenuForEntry(EItem.Remote, "origin")

    findMenuAction(menu, "edit remote").trigger()

    q: RemoteDialog = findQDialog(rw, "edit remote")
    q.ui.nameEdit.setText("mainremote")
    q.ui.urlEdit.setText("https://127.0.0.1/example-repo.git")
    q.accept()

    assert len(repo.remotes) == 1
    assert repo.remotes[0].name == "mainremote"
    assert repo.remotes[0].url == "https://127.0.0.1/example-repo.git"


def testDeleteRemote(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    repo = rw.repo

    assert repo.remotes["origin"] is not None

    menu = rw.sidebar.generateMenuForEntry(EItem.Remote, "origin")

    findMenuAction(menu, "delete remote").trigger()
    acceptQMessageBox(rw, "really delete remote")

    assert len(list(repo.remotes)) == 0


