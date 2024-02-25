import pygit2.enums

from gitfourchette.nav import NavLocator
from .test_tasks_stage import doStage, doDiscard
from . import reposcenario
from .util import *
from gitfourchette.sidebar.sidebarmodel import EItem
import os
import pytest


@pytest.mark.parametrize("method", ["sidebar", "commitSpecialDiff", "commitFileList", "dirtyFileList", "stagedFileList"])
def testOpenSubmoduleWithinApp(tempDir, mainWindow, method):
    wd = unpackRepo(tempDir)
    submoAbsPath, submoCommit = reposcenario.submodule(wd)
    writeFile(f"{submoAbsPath}/dirty.txt", "coucou")

    rw = mainWindow.openRepo(wd)
    assert mainWindow.currentRepoWidget() is rw

    if method == "sidebar":
        submoNode = next(rw.sidebar.findNodesByKind(EItem.Submodule))
        assert "submo" == submoNode.data
        menu = rw.sidebar.makeNodeMenu(submoNode)
        triggerMenuAction(menu, r"open submodule.+tab")

    elif method == "commitSpecialDiff":
        rw.jump(NavLocator.inCommit(oid=submoCommit, path="submo"))
        assert rw.specialDiffView.isVisibleTo(rw)
        assert qteFind(rw.specialDiffView, r"submodule.+submo.+was added")
        qteClickLink(rw.specialDiffView, r"open submodule.+submo")

    elif method == "commitFileList":
        rw.jump(NavLocator.inCommit(oid=submoCommit, path="submo"))
        menu = rw.committedFiles.makeContextMenu()
        triggerMenuAction(menu, r"open.+submodule.+in new tab")

    elif method == "dirtyFileList":
        rw.jump(NavLocator.inUnstaged(path="submo"))
        menu = rw.dirtyFiles.makeContextMenu()
        triggerMenuAction(menu, r"open.+submodule.+in new tab")

    elif method == "stagedFileList":
        with RepoContext(submoAbsPath, write_index=True) as submoRepo:
            submoRepo.reset(Oid(hex="ac7e7e44c1885efb472ad54a78327d66bfc4ecef"), ResetMode.HARD)
        rw.repo.index.add("submo")
        rw.refreshRepo()

        rw.jump(NavLocator.inStaged(path="submo"))
        menu = rw.stagedFiles.makeContextMenu()
        triggerMenuAction(menu, r"open.+submodule.+in new tab")

    else:
        raise NotImplementedError("unknown method")

    assert mainWindow.currentRepoWidget() is not rw
    assert mainWindow.currentRepoWidget().repo.workdir == submoAbsPath + "/"


@pytest.mark.parametrize("method", ["key", "menu", "button"])
def testSubmoduleHeadUpdate(tempDir, mainWindow, method):
    wd = unpackRepo(tempDir)
    subWd, _ = reposcenario.submodule(wd)
    subHead = Oid(hex='49322bb17d3acc9146f98c97d078513228bbf3c0')
    with RepoContext(subWd) as submo:
        submo.checkout_commit(subHead)

    rw = mainWindow.openRepo(wd)

    assert qlvGetRowData(rw.dirtyFiles) == ["submo"]
    assert qlvClickNthRow(rw.dirtyFiles, 0)

    special = rw.specialDiffView
    assert special.isVisibleTo(rw)
    assert qteFind(special, r"submodule.+submo.+was updated")
    assert qteFind(special, r"new:\s+49322bb", plainText=True)

    doStage(rw, method)

    assert qlvGetRowData(rw.dirtyFiles) == []
    assert qlvGetRowData(rw.stagedFiles) == ["submo"]


@pytest.mark.parametrize("method", ["key", "menu", "button", "link"])
def testSubmoduleDirty(tempDir, mainWindow, method):
    wd = unpackRepo(tempDir)
    subWd, _ = reposcenario.submodule(wd)
    writeFile(f"{subWd}/dirty.txt", "coucou")

    rw = mainWindow.openRepo(wd)

    assert rw.repo.status() == {"submo": FileStatus.WT_MODIFIED}
    assert qlvClickNthRow(rw.dirtyFiles, 0)

    special = rw.specialDiffView
    assert special.isVisibleTo(rw)
    assert qteFind(special, r"submodule.+submo.+was updated")
    assert qteFind(special, r"uncommitted changes")

    QTest.keyPress(rw.dirtyFiles, Qt.Key.Key_Return)  # attempt to stage it
    assert rw.repo.status() == {"submo": FileStatus.WT_MODIFIED}  # shouldn't do anything (the actual app will emit a beep)

    if method == "link":
        qteClickLink(special, r"discard them\.")
    else:
        doDiscard(rw, method)

    acceptQMessageBox(rw, r"discard changes in submodule.+submo.+uncommitted changes")
    assert rw.repo.status() == {}  # should've cleared everything


def testSubmoduleDeletedDiff(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    subWd, subAddOid = reposcenario.submodule(wd)
    with RepoContext(wd) as repo:
        shutil.rmtree(f"{wd}/submo")
        os.unlink(f"{wd}/.gitmodules")
        repo.index.remove(".gitmodules")
        repo.index.remove("submo")
        subDelOid = repo.create_commit_on_head("delete submo")

    rw = mainWindow.openRepo(wd)

    assert not rw.repo.listall_submodules()
    assert [] == list(rw.sidebar.findNodesByKind(EItem.Submodule))

    rw.jump(NavLocator.inCommit(subAddOid, path="submo"))
    assert rw.specialDiffView.isVisibleTo(rw)
    assert re.search(r"submodule.+submo.+added", rw.specialDiffView.toPlainText(), re.I)

    rw.jump(NavLocator.inCommit(subDelOid, path="submo"))
    assert rw.specialDiffView.isVisibleTo(rw)
    assert re.search(r"submodule.+submo.+(deleted|removed)", rw.specialDiffView.toPlainText(), re.I)


def testDeleteSubmodule(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    reposcenario.submodule(wd)
    rw = mainWindow.openRepo(wd)

    node = rw.sidebar.findNode(lambda n: n.data == "submo")
    assert node.kind == EItem.Submodule
    menu = rw.sidebar.makeNodeMenu(node)
    triggerMenuAction(menu, r"remove submodule")

    acceptQMessageBox(rw, r"remove submodule")
    assert not list(rw.sidebar.findNodesByKind(EItem.Submodule))
    assert set(qlvGetRowData(rw.stagedFiles)) == {"submo", ".gitmodules"}


def testAbsorbSubmodule(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    subWd = unpackRepo(wd, renameTo="submo")
    rw = mainWindow.openRepo(wd)
    assert rw.isVisibleTo(mainWindow)

    # Start without any submodules
    assert [] == rw.repo.listall_submodules_fast()
    assert [] == list(rw.sidebar.findNodesByKind(EItem.Submodule))

    # Select subfolder in dirty files
    rw.jump(NavLocator.inUnstaged("submo"))
    assert rw.specialDiffView.isVisibleTo(rw)
    assert "root of another git repo" in rw.specialDiffView.toPlainText().lower()

    # Click "absorb 'submo' as submodule" link
    foundLink = rw.specialDiffView.find(QRegularExpression(r"absorb.+as submodule"))
    assert foundLink
    QTest.keyPress(rw.specialDiffView, Qt.Key.Key_Enter)

    # Let AbsorbSubmodule run to completion
    dlg = findQDialog(rw, "absorb.+submodule")
    dlg.accept()

    # There must be a submodule now
    assert ["submo"] == rw.repo.listall_submodules_fast()
    assert "submo" == next(rw.sidebar.findNodesByKind(EItem.Submodule)).data

    # The submodule is there, but it's unstaged
    rw.jump(NavLocator.inStaged("submo"))

    # Click "open submodule" link
    qteClickLink(rw.specialDiffView, "open submodule")

    # That must have opened a new tab
    assert not rw.isVisibleTo(mainWindow)
    assert 2 == len(mainWindow.tabs)
    assert 1 == mainWindow.tabs.currentIndex()

    # Open superproject from tab context menu
    mainWindow.tabs.tabContextMenuRequested.emit(QPoint(0, 0), 1)
    tabMenu = mainWindow.findChild(QMenu, "MWRepoTabContextMenu")
    triggerMenuAction(tabMenu, r"open superproject")
    assert 0 == mainWindow.tabs.currentIndex()  # back to first tab
    assert rw is mainWindow.tabs.currentWidget()  # back to first tab
