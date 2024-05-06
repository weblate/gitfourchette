"""
Remote management tests.
"""

import pytest
from . import reposcenario
from .util import *
from gitfourchette.forms.remotedialog import RemoteDialog
from gitfourchette.sidebar.sidebarmodel import EItem


@pytest.mark.parametrize("method", ["menubar", "sidebarmenu", "sidebarkey"])
def testNewRemote(tempDir, mainWindow, method):
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

    if method == "menubar":
        triggerMenuAction(mainWindow.menuBar(), "repo/add remote")
    elif method == "sidebarmenu":
        menu = rw.sidebar.makeNodeMenu(node)
        triggerMenuAction(menu, "add remote")
    elif method == "sidebarkey":
        rw.sidebar.selectNode(node)
        QTest.keyPress(rw.sidebar, Qt.Key.Key_Enter)
    else:
        raise NotImplementedError(f"unknown method {method}")

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


@pytest.mark.parametrize("method", ["sidebarmenu", "sidebarkey1", "sidebarkey2"])
def testEditRemote(tempDir, mainWindow, method):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    repo = rw.repo

    # Ensure we're starting with the expected settings
    assert len(repo.remotes) == 1
    assert repo.remotes[0].name == "origin"
    assert any("/origin/" in n.data for n in rw.sidebar.findNodesByKind(EItem.RemoteBranch))

    node = rw.sidebar.findNode(lambda n: n.kind == EItem.Remote and n.data == "origin")

    toolTip = node.createIndex(rw.sidebar.sidebarModel).data(Qt.ItemDataRole.ToolTipRole)
    assert "https://github.com/libgit2/TestGitRepository" in toolTip

    if method == "sidebarmenu":
        menu = rw.sidebar.makeNodeMenu(node)
        triggerMenuAction(menu, "edit remote")
    elif method == "sidebarkey1":
        rw.sidebar.selectNode(node)
        QTest.keyPress(rw.sidebar, Qt.Key.Key_F2)
    elif method == "sidebarkey2":
        rw.sidebar.selectNode(node)
        QTest.keyPress(rw.sidebar, Qt.Key.Key_Enter)
    else:
        raise NotImplementedError(f"unknown method {method}")

    q: RemoteDialog = findQDialog(rw, "edit remote")
    q.ui.nameEdit.setText("mainremote")
    q.ui.urlEdit.setText("https://127.0.0.1/example-repo.git")
    q.accept()

    assert len(repo.remotes) == 1
    assert repo.remotes[0].name == "mainremote"
    assert repo.remotes[0].url == "https://127.0.0.1/example-repo.git"
    assert any("/mainremote/" in n.data for n in rw.sidebar.findNodesByKind(EItem.RemoteBranch))
    assert not any("/origin/" in n.data for n in rw.sidebar.findNodesByKind(EItem.RemoteBranch))


@pytest.mark.parametrize("method", ["sidebarmenu", "sidebarkey"])
def testDeleteRemote(tempDir, mainWindow, method):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    repo = rw.repo

    assert repo.remotes["origin"] is not None
    assert any("/origin/" in n.data for n in rw.sidebar.findNodesByKind(EItem.RemoteBranch))

    node = rw.sidebar.findNode(lambda n: n.kind == EItem.Remote and n.data == "origin")

    if method == "sidebarmenu":
        menu = rw.sidebar.makeNodeMenu(node)
        triggerMenuAction(menu, "remove remote")
    elif method == "sidebarkey":
        rw.sidebar.selectNode(node)
        QTest.keyPress(rw.sidebar, Qt.Key.Key_Delete)
    else:
        raise NotImplementedError(f"unknown method {method}")

    acceptQMessageBox(rw, "really remove remote")

    assert len(list(repo.remotes)) == 0
    assert not any("/origin/" in n.data for n in rw.sidebar.findNodesByKind(EItem.RemoteBranch))
