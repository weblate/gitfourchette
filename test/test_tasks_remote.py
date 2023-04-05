"""
Remote management tests.
"""

from . import reposcenario
from .fixtures import *
from .util import *
from gitfourchette.forms.remotedialog import RemoteDialog
from gitfourchette.sidebar.sidebarmodel import EItem


def testNewRemote(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    repo = rw.repo

    # Ensure we're starting with the expected settings
    assert len(repo.remotes) == 1
    assert repo.remotes[0].name == "origin"
    assert "origin" in rw.sidebar.datasForItemType(EItem.Remote)
    assert "otherremote" not in rw.sidebar.datasForItemType(EItem.Remote)

    menu = rw.sidebar.generateMenuForEntry(EItem.RemotesHeader)

    findMenuAction(menu, "add remote").trigger()

    q: RemoteDialog = findQDialog(rw, "add remote")
    q.ui.nameEdit.setText("otherremote")
    q.ui.urlEdit.setText("https://127.0.0.1/example-repo.git")
    q.accept()

    assert len(repo.remotes) == 2
    assert repo.remotes[1].name == "otherremote"
    assert repo.remotes[1].url == "https://127.0.0.1/example-repo.git"
    assert "origin" in rw.sidebar.datasForItemType(EItem.Remote)
    assert "otherremote" in rw.sidebar.datasForItemType(EItem.Remote)


def testEditRemote(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    repo = rw.repo

    # Ensure we're starting with the expected settings
    assert len(repo.remotes) == 1
    assert repo.remotes[0].name == "origin"
    assert any(userData.startswith("origin/") for userData in rw.sidebar.datasForItemType(EItem.RemoteBranch))

    menu = rw.sidebar.generateMenuForEntry(EItem.Remote, "origin")

    findMenuAction(menu, "edit remote").trigger()

    q: RemoteDialog = findQDialog(rw, "edit remote")
    q.ui.nameEdit.setText("mainremote")
    q.ui.urlEdit.setText("https://127.0.0.1/example-repo.git")
    q.accept()

    assert len(repo.remotes) == 1
    assert repo.remotes[0].name == "mainremote"
    assert repo.remotes[0].url == "https://127.0.0.1/example-repo.git"
    assert any(userData.startswith("mainremote/") for userData in rw.sidebar.datasForItemType(EItem.RemoteBranch))
    assert not any(userData.startswith("origin/") for userData in rw.sidebar.datasForItemType(EItem.RemoteBranch))


def testDeleteRemote(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    repo = rw.repo

    assert repo.remotes["origin"] is not None
    assert any(userData.startswith("origin/") for userData in rw.sidebar.datasForItemType(EItem.RemoteBranch))

    menu = rw.sidebar.generateMenuForEntry(EItem.Remote, "origin")

    findMenuAction(menu, "remove remote").trigger()
    acceptQMessageBox(rw, "really remove remote")

    assert len(list(repo.remotes)) == 0
    assert not any(userData.startswith("origin/") for userData in rw.sidebar.datasForItemType(EItem.RemoteBranch))

