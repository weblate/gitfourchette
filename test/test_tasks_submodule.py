import os
import shutil

import pygit2
import pytest
from pygit2.enums import SubmoduleStatus

from gitfourchette.nav import NavLocator
from gitfourchette.sidebar.sidebarmodel import EItem
from . import reposcenario
from .test_tasks_stage import doStage, doDiscard
from .util import *


@pytest.mark.parametrize("method", ["sidebarMenu", "sidebarKey", "sidebarDClick", "commitSpecialDiff", "commitFileList", "dirtyFileList", "stagedFileList"])
def testOpenSubmoduleWithinApp(tempDir, mainWindow, method):
    wd = unpackRepo(tempDir)
    submoAbsPath, submoCommit = reposcenario.submodule(wd)
    writeFile(f"{submoAbsPath}/dirty.txt", "coucou")

    rw = mainWindow.openRepo(wd)
    assert mainWindow.currentRepoWidget() is rw

    submoNode = next(rw.sidebar.findNodesByKind(EItem.Submodule))
    assert "submoname" == submoNode.data

    if method == "sidebarMenu":
        menu = rw.sidebar.makeNodeMenu(submoNode)
        triggerMenuAction(menu, r"open submodule.+tab")

    elif method == "sidebarKey":
        rw.sidebar.selectNode(submoNode)
        QTest.keyPress(rw.sidebar, Qt.Key.Key_Return)

    elif method == "sidebarDClick":
        rect = rw.sidebar.visualRect(submoNode.createIndex(rw.sidebar.sidebarModel))
        QTest.mouseDClick(rw.sidebar.viewport(), Qt.MouseButton.LeftButton, pos=rect.topLeft())

    elif method == "commitSpecialDiff":
        rw.jump(NavLocator.inCommit(oid=submoCommit, path="submodir"))
        assert rw.specialDiffView.isVisibleTo(rw)
        assert qteFind(rw.specialDiffView, r"submodule.+submo.+was added")
        qteClickLink(rw.specialDiffView, r"open submodule.+submo")

    elif method == "commitFileList":
        rw.jump(NavLocator.inCommit(oid=submoCommit, path="submodir"))
        menu = rw.committedFiles.makeContextMenu()
        triggerMenuAction(menu, r"open.+submodule.+in new tab")

    elif method == "dirtyFileList":
        rw.jump(NavLocator.inUnstaged(path="submodir"))
        menu = rw.dirtyFiles.makeContextMenu()
        triggerMenuAction(menu, r"open.+submodule.+in new tab")

    elif method == "stagedFileList":
        with RepoContext(submoAbsPath, write_index=True) as submoRepo:
            submoRepo.reset(Oid(hex="ac7e7e44c1885efb472ad54a78327d66bfc4ecef"), ResetMode.HARD)
        rw.repo.index.add("submodir")
        rw.refreshRepo()

        rw.jump(NavLocator.inStaged(path="submodir"))
        menu = rw.stagedFiles.makeContextMenu()
        triggerMenuAction(menu, r"open.+submodule.+in new tab")

    else:
        raise NotImplementedError("unknown method")

    if WINDOWS:
        submoAbsPath = submoAbsPath.replace("\\", "/")

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

    assert qlvGetRowData(rw.dirtyFiles) == ["submodir"]
    assert qlvClickNthRow(rw.dirtyFiles, 0)

    special = rw.specialDiffView
    assert special.isVisibleTo(rw)
    assert qteFind(special, r"submodule.+submoname.+was updated")
    assert qteFind(special, r"new:\s+49322bb", plainText=True)

    doStage(rw, method)

    assert qlvGetRowData(rw.dirtyFiles) == []
    assert qlvGetRowData(rw.stagedFiles) == ["submodir"]


@pytest.mark.parametrize("method", ["key", "menu", "button", "link"])
def testSubmoduleDirty(tempDir, mainWindow, method):
    wd = unpackRepo(tempDir)
    subWd, _ = reposcenario.submodule(wd)
    writeFile(f"{subWd}/dirty.txt", "coucou")

    rw = mainWindow.openRepo(wd)

    assert rw.repo.status() == {"submodir": FileStatus.WT_MODIFIED}
    assert qlvClickNthRow(rw.dirtyFiles, 0)

    special = rw.specialDiffView
    assert special.isVisibleTo(rw)
    assert qteFind(special, r"submodule.+submo.+was updated")
    assert qteFind(special, r"uncommitted changes")

    QTest.keyPress(rw.dirtyFiles, Qt.Key.Key_Return)  # attempt to stage it
    assert rw.repo.status() == {"submodir": FileStatus.WT_MODIFIED}  # shouldn't do anything (the actual app will emit a beep)

    if method == "link":
        qteClickLink(special, r"reset")
    else:
        doDiscard(rw, method)

    acceptQMessageBox(rw, r"discard changes in submodule.+submo.+uncommitted changes")
    assert rw.repo.status() == {}  # should've cleared everything


def testSubmoduleDeletedDiff(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    subWd, subAddId = reposcenario.submodule(wd)
    with RepoContext(wd) as repo:
        shutil.rmtree(f"{wd}/submodir")
        os.unlink(f"{wd}/.gitmodules")
        repo.index.remove(".gitmodules")
        repo.index.remove("submodir")
        subDelId = repo.create_commit_on_head("delete submo")

    rw = mainWindow.openRepo(wd)

    assert not rw.repo.listall_submodules_dict()
    assert [] == list(rw.sidebar.findNodesByKind(EItem.Submodule))

    rw.jump(NavLocator.inCommit(subAddId, path="submodir"))
    assert rw.specialDiffView.isVisibleTo(rw)
    assert re.search(r"submodule.+submo.+added", rw.specialDiffView.toPlainText(), re.I)

    rw.jump(NavLocator.inCommit(subDelId, path="submodir"))
    assert rw.specialDiffView.isVisibleTo(rw)
    assert re.search(r"submodule.+submo.+(deleted|removed)", rw.specialDiffView.toPlainText(), re.I)


def testDeleteSubmodule(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    reposcenario.submodule(wd)
    rw = mainWindow.openRepo(wd)

    node = rw.sidebar.findNode(lambda n: n.data == "submoname")
    assert node.kind == EItem.Submodule
    menu = rw.sidebar.makeNodeMenu(node)
    triggerMenuAction(menu, r"remove submodule")

    acceptQMessageBox(rw, r"remove submodule")
    assert not list(rw.sidebar.findNodesByKind(EItem.Submodule))
    assert set(qlvGetRowData(rw.stagedFiles)) == {"submodir", ".gitmodules"}


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


def testDeleteAbsorbedSubmoduleThenRestoreIt(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    reposcenario.submodule(wd, absorb=True)

    rw = mainWindow.openRepo(wd)

    assert rw.repo.config["submodule.submoname.url"]

    # Delete the submodule
    node = next(rw.sidebar.findNodesByKind(EItem.Submodule))
    assert node.data == "submoname"
    menu = rw.sidebar.makeNodeMenu(node)
    triggerMenuAction(menu, "remove")
    acceptQMessageBox(rw, "remove submodule")

    with pytest.raises(KeyError): rw.repo.config["submodule.submoname.url"]
    assert not list(rw.sidebar.findNodesByKind(EItem.Submodule))
    assert set(qlvGetRowData(rw.stagedFiles)) == {".gitmodules", "submodir"}

    # Discard submodule deletion
    qlvClickNthRow(rw.stagedFiles, 0)  # TODO: selectAll won't actually select everything without this first
    rw.stagedFiles.selectAll()
    rw.stagedFiles.unstage()
    qlvClickNthRow(rw.dirtyFiles, 0)  # TODO: selectAll won't actually select everything without this first
    rw.dirtyFiles.selectAll()
    rw.dirtyFiles.discard()
    acceptQMessageBox(rw, "discard changes")

    node = next(rw.sidebar.findNodesByKind(EItem.Submodule))
    assert node.data == "submoname"
    menu = rw.sidebar.makeNodeMenu(node)
    triggerMenuAction(menu, "update")


def testInitSubmoduleInFreshNonRecursiveClone(tempDir, mainWindow):
    sm = "submosub"

    # Unpack full-blown repo (complete with submodule) as our upstream
    upstreamWd = unpackRepo(tempDir, "submoroot", renameTo="upstream")
    upstreamSub = f"{upstreamWd}/{sm}"

    # Do a non-recursive clone (using the local filesystem as an upstream)
    repo = pygit2.clone_repository(upstreamWd, f"{tempDir.name}/submoroot")
    wd = repo.workdir
    repo.free()
    del repo

    # Prevent submo from hitting network
    # NOTE: We're modifying .gitmodules, NOT .git/config, so that the module appears UNinitialized!
    GitConfig(f"{wd}/.gitmodules")[f"submodule.{sm}.url"] = upstreamSub
    assert f"submodule.{sm}.url" not in GitConfig(f"{wd}/.git/config")

    # Open the repo
    rw = mainWindow.openRepo(wd)
    repo = rw.repo

    # At this point the submodule isn't initialized and its worktree is empty
    assert [] == os.listdir(f"{wd}/{sm}")
    assert repo.submodules.status(sm) & SubmoduleStatus.WD_UNINITIALIZED

    node = next(rw.sidebar.findNodesByKind(EItem.Submodule))
    assert node.data == sm
    menu = rw.sidebar.makeNodeMenu(node)
    triggerMenuAction(menu, "init")

    assert ".git" in os.listdir(f"{wd}/{sm}")
    assert not repo.submodules.status(sm) & SubmoduleStatus.WD_UNINITIALIZED


@pytest.mark.skipif(pygit2OlderThan("1.15.1"), reason="old pygit2")
def testUpdateSubmoduleWithMissingIncomingCommit(tempDir, mainWindow):
    sm = "submosub"

    # Unpack full-blown repo (complete with submodule) as our upstream
    upstreamWd = unpackRepo(tempDir, "submoroot", renameTo="upstream")
    upstreamSub = f"{upstreamWd}/{sm}"

    # Do a non-recursive clone (using the local filesystem as an upstream) and init the submodule
    repo = pygit2.clone_repository(upstreamWd, f"{tempDir.name}/submoroot")
    wd = repo.workdir
    GitConfig(f"{wd}/.git/config")[f"submodule.{sm}.url"] = upstreamSub  # don't hit the network during update!
    repo.submodules.update(init=True)
    repo.free()
    del repo

    # Create new commit in UPSTREAM submo
    with RepoContext(upstreamSub, write_index=True) as sub:
        oldSubCommit = sub.head_commit_id
        writeFile(f"{upstreamSub}/foo.txt", "bar baz")
        sub.index.add("foo.txt")
        newSubCommit = sub.create_commit_on_head("yet another new commit in submodule", TEST_SIGNATURE, TEST_SIGNATURE)

    # In the outer repo, create a commit that moves the submodule's HEAD to newSubCommit.
    # (i.e. simulate a scenario where the user does a non-recursive fetch of the root repo,
    # and they receive this commit, but they don't have newSubCommit in the submodule)
    with RepoContext(wd, write_index=True) as repo:
        treeBuilder = repo.TreeBuilder(repo.head_tree.id)
        treeBuilder.insert(sm, newSubCommit, FileMode.COMMIT)
        newTreeId = treeBuilder.write()
        newTree = repo[newTreeId].peel(Tree)
        repo.index.read_tree(newTree)
        repo.create_commit("HEAD", TEST_SIGNATURE, TEST_SIGNATURE, f"move submo to {str(newSubCommit)[:7]}",
                           newTreeId, [repo.head_commit_id])

    # Now open the outer repo...
    rw = mainWindow.openRepo(wd)

    # The submodule will appear as dirty; the diff says that the submodule's head is being moved
    # from newSubCommit to the previous commit. This tracks with vanilla git status.
    # In fact, the submodule's gitlink file points to our local copy of the submodule,
    # which is indeed still on the previous commit, so this technically makes sense (although unintuitive).
    assert sm in qlvGetRowData(rw.dirtyFiles)
    assert sm not in qlvGetRowData(rw.stagedFiles)
    rw.jump(NavLocator.inUnstaged(sm))
    newHash = str(newSubCommit)[:7]
    oldHash = str(oldSubCommit)[:7]
    assert qteFind(rw.specialDiffView, fr"old.+{newHash}.+new.+{oldHash}", True)  # yes, old/new look inverted, that's on purpose

    # Update the submodule
    node = next(rw.sidebar.findNodesByKind(EItem.Submodule))
    assert node.data == sm
    menu = rw.sidebar.makeNodeMenu(node)
    triggerMenuAction(menu, "update")

    QTest.qWait(1)
    assert sm not in qlvGetRowData(rw.dirtyFiles)
    assert sm not in qlvGetRowData(rw.stagedFiles)


@pytest.mark.skipif(pygit2OlderThan("1.15.1"), reason="old pygit2")
@pytest.mark.parametrize("recurse", [True, False])
@pytest.mark.parametrize("method", ["switch1", "switch2", "detach", "newbranch"])
def testSwitchBranchAskRecurse(tempDir, mainWindow, method, recurse):
    oid = Oid(hex="ea953d3ba4c5326d530dc09b4ca9781b01c18e00")
    contentsHead = b"hello from submodule\nan update!\n"
    contentsOld = b"hello from submodule\n"

    wd = unpackRepo(tempDir, "submoroot")

    with RepoContext(wd) as repo:
        repo.create_branch_from_commit("old", oid)

    rw = mainWindow.openRepo(wd)
    assert contentsHead == readFile(f"{wd}/submosub/subhello.txt")

    node = rw.sidebar.findNodeByRef("refs/heads/old")
    rw.jump(NavLocator.inCommit(oid))

    if method == "switch1":
        triggerMenuAction(rw.sidebar.makeNodeMenu(node), "switch")
        qmb = findQMessageBox(rw, "switch to")
        assert "submodule" in qmb.checkBox().text().lower()
        assert qmb.checkBox().isChecked()
        qmb.checkBox().setChecked(recurse)
        qmb.accept()
    elif method == "newbranch":
        triggerMenuAction(rw.sidebar.makeNodeMenu(node), "new branch")
        dlg = findQDialog(rw, "new branch")
        dlg.ui.nameEdit.setText("blahblah")
        assert dlg.ui.recurseSubmodulesCheckBox.isVisible()
        assert dlg.ui.recurseSubmodulesCheckBox.isChecked()
        dlg.ui.recurseSubmodulesCheckBox.setChecked(recurse)
        dlg.accept()
    elif method == "switch2":
        triggerMenuAction(rw.graphView.makeContextMenu(), "check.?out")
        dlg = findQDialog(rw, "check.?out")
        assert dlg.ui.switchToLocalBranchRadioButton.isChecked()
        assert dlg.ui.recurseSubmodulesCheckBox.isVisible()
        assert dlg.ui.recurseSubmodulesCheckBox.isChecked()
        dlg.ui.recurseSubmodulesCheckBox.setChecked(recurse)
        dlg.accept()
    elif method == "detach":
        triggerMenuAction(rw.graphView.makeContextMenu(), "check.?out")
        dlg = findQDialog(rw, "check.?out")
        dlg.ui.detachedHeadRadioButton.setChecked(True)
        dlg.ui.recurseSubmodulesCheckBox.setChecked(recurse)
        dlg.accept()
    else:
        raise NotImplementedError("unsupported method")

    if recurse:
        assert contentsOld == readFile(f"{wd}/submosub/subhello.txt")
    else:
        assert contentsHead == readFile(f"{wd}/submosub/subhello.txt")
