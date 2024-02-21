"""
Remote management tests.
"""

from . import reposcenario
from .util import *
from gitfourchette.forms.remotedialog import RemoteDialog
from gitfourchette.sidebar.sidebarmodel import EItem


def testNewRemote(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    repo = rw.repo

    # Make a bare copy of the repo to use as a remote "server"
    barePath = makeBareCopy(wd, addAsRemote="", preFetch=False)

    # Ensure we're starting with the expected settings
    assert len(repo.remotes) == 1
    assert repo.remotes[0].name == "origin"
    assert any("origin" == n.data for n in rw.sidebar.findNodesByKind(EItem.Remote))
    assert not any("otherremote" == n.data for n in rw.sidebar.findNodesByKind(EItem.Remote))

    node = next(rw.sidebar.findNodesByKind(EItem.RemotesHeader))
    menu = rw.sidebar.makeNodeMenu(node)

    findMenuAction(menu, "add remote").trigger()

    q: RemoteDialog = findQDialog(rw, "add remote")
    q.ui.nameEdit.setText("otherremote")
    q.ui.urlEdit.setText(barePath)
    q.ui.fetchAfterAddCheckBox.setChecked(True)
    q.accept()

    assert len(repo.remotes) == 2
    assert repo.remotes[1].name == "otherremote"
    assert repo.remotes[1].url == barePath
    assert any("origin" == n.data for n in rw.sidebar.findNodesByKind(EItem.Remote))
    assert any("otherremote" == n.data for n in rw.sidebar.findNodesByKind(EItem.Remote))

    # Ensure that fetch-after-add did work
    assert repo.branches.remote["otherremote/master"].target == repo.branches.local["master"].target


def testEditRemote(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    repo = rw.repo

    # Ensure we're starting with the expected settings
    assert len(repo.remotes) == 1
    assert repo.remotes[0].name == "origin"
    assert any("/origin/" in n.data for n in rw.sidebar.findNodesByKind(EItem.RemoteBranch))

    node = rw.sidebar.findNode(lambda n: n.kind == EItem.Remote and n.data == "origin")
    menu = rw.sidebar.makeNodeMenu(node)
    triggerMenuAction(menu, "edit remote")

    q: RemoteDialog = findQDialog(rw, "edit remote")
    q.ui.nameEdit.setText("mainremote")
    q.ui.urlEdit.setText("https://127.0.0.1/example-repo.git")
    q.accept()

    assert len(repo.remotes) == 1
    assert repo.remotes[0].name == "mainremote"
    assert repo.remotes[0].url == "https://127.0.0.1/example-repo.git"
    assert any("/mainremote/" in n.data for n in rw.sidebar.findNodesByKind(EItem.RemoteBranch))
    assert not any("/origin/" in n.data for n in rw.sidebar.findNodesByKind(EItem.RemoteBranch))


def testDeleteRemote(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    repo = rw.repo

    assert repo.remotes["origin"] is not None
    assert any("/origin/" in n.data for n in rw.sidebar.findNodesByKind(EItem.RemoteBranch))

    node = rw.sidebar.findNode(lambda n: n.kind == EItem.Remote and n.data == "origin")
    menu = rw.sidebar.makeNodeMenu(node)
    triggerMenuAction(menu, "remove remote")
    acceptQMessageBox(rw, "really remove remote")

    assert len(list(repo.remotes)) == 0
    assert not any("/origin/" in n.data for n in rw.sidebar.findNodesByKind(EItem.RemoteBranch))

