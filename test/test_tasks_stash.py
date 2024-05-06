from . import reposcenario
from .util import *
from gitfourchette.sidebar.sidebarmodel import EItem
from gitfourchette.forms.stashdialog import StashDialog
from gitfourchette.tasks import DropStash
import os
import pytest


def testNewStash(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    writeFile(F"{wd}/a/a1.txt", "a1\nPENDING CHANGE\n")  # unstaged change
    writeFile(F"{wd}/b/b1.txt", "b1\nPENDING CHANGE (staged)\n")  # staged change
    writeFile(F"{wd}/a/untracked.txt", "this file is untracked\n")  # untracked file
    with RepoContext(wd, write_index=True) as repo:
        repo.index.add("b/b1.txt")
    rw = mainWindow.openRepo(wd)
    sb = rw.sidebar
    repo = rw.repo

    assert len(repo.listall_stashes()) == 0

    assert not list(sb.findNodesByKind(EItem.Stash))
    assert qlvGetRowData(rw.dirtyFiles) == ["a/a1.txt", "a/untracked.txt"]
    assert qlvGetRowData(rw.stagedFiles) == ["b/b1.txt"]

    node = next(sb.findNodesByKind(EItem.StashesHeader))
    menu = sb.makeNodeMenu(node)
    triggerMenuAction(menu, "stash changes")

    dlg: StashDialog = findQDialog(rw, "new stash")
    assert not dlg.ui.keepCheckBox.isChecked()
    dlg.ui.messageEdit.setText("helloworld")
    dlg.accept()

    assert not os.path.isfile(f"{wd}/a/untracked.txt"), "untracked file must be gone after stashing"
    assert qlvGetRowData(rw.dirtyFiles) == [], "workdir must be clean after stashing"
    assert qlvGetRowData(rw.stagedFiles) == [], "workdir must be clean after stashing"
    assert len(repo.listall_stashes()) == 1, "there must be one stash in the repo"

    stashNode = sb.findNodeByRef("stash@{0}")
    stashNodeIndex = stashNode.createIndex(sb.sidebarModel)
    assert "helloworld" == stashNodeIndex.data(Qt.ItemDataRole.DisplayRole)
    assert "helloworld" in stashNodeIndex.data(Qt.ItemDataRole.ToolTipRole)

    rw.selectRef("refs/stash")
    assert rw.committedFiles.isVisibleTo(rw)
    assert qlvGetRowData(rw.committedFiles) == ["a/a1.txt", "a/untracked.txt", "b/b1.txt"]


@pytest.mark.parametrize("method", ["stashcommand", "filelist"])
def testNewPartialStash(tempDir, mainWindow, method):
    wd = unpackRepo(tempDir)
    writeFile(F"{wd}/a/a1.txt", "a1\nPENDING CHANGE 1\n")  # unstaged change
    writeFile(F"{wd}/a/a2.txt", "a2\nPENDING CHANGE 2\n")  # unstaged change
    writeFile(F"{wd}/b/b1.txt", "b1\nPENDING CHANGE (staged)\n")  # staged change
    writeFile(F"{wd}/a/untracked1.txt", "this file is untracked 1\n")  # untracked file
    writeFile(F"{wd}/a/untracked2.txt", "this file is untracked 2\n")  # untracked file
    with RepoContext(wd, write_index=True) as repo:
        repo.index.add("b/b1.txt")
    rw = mainWindow.openRepo(wd)
    repo = rw.repo

    dirtyFiles = ["a/a1.txt", "a/a2.txt", "a/untracked1.txt", "a/untracked2.txt"]
    stagedFiles = ["b/b1.txt"]
    stashedFiles = ["a/a2.txt", "a/untracked2.txt"]
    keptFiles = sorted(set(dirtyFiles + stagedFiles) - set(stashedFiles))

    assert len(repo.listall_stashes()) == 0

    assert 0 == len(list(rw.sidebar.findNodesByKind(EItem.Stash)))
    assert qlvGetRowData(rw.dirtyFiles) == dirtyFiles

    if method == "stashcommand":
        node = next(rw.sidebar.findNodesByKind(EItem.StashesHeader))
        menu = rw.sidebar.makeNodeMenu(node)
        triggerMenuAction(menu, "stash changes")
    elif method == "filelist":
        rw.dirtyFiles.clearSelection()
        for file in stashedFiles:
            row = qlvFindRow(rw.dirtyFiles, file)
            index = rw.dirtyFiles.flModel.index(row, 0)
            rw.dirtyFiles.selectionModel().select(index, QItemSelectionModel.SelectionFlag.Select)
        cm = rw.dirtyFiles.makeContextMenu()
        triggerMenuAction(cm, "stash")
    else:
        raise NotImplementedError(f"unknown method {method}")

    dlg: StashDialog = findQDialog(rw, "new stash")
    assert not dlg.ui.keepCheckBox.isChecked()
    dlg.ui.messageEdit.setText("helloworld")

    fl = dlg.ui.fileList
    assert sorted(qlvGetRowData(fl)) == sorted(dirtyFiles + stagedFiles)

    # Uncheck some files to produce a partial stash
    if method == "stashcommand":
        for uncheckFile in keptFiles:
            row = qlvFindRow(fl, uncheckFile)
            qlvClickNthRow(fl, row)
            fl.selectedItems()[0].setCheckState(Qt.CheckState.Unchecked)

    dlg.accept()

    assert os.path.isfile(f"{wd}/a/untracked1.txt"), "untracked file 1 should still be here"
    assert not os.path.isfile(f"{wd}/a/untracked2.txt"), "untracked file 2 must be gone"
    assert keptFiles == sorted(qlvGetRowData(rw.dirtyFiles) + qlvGetRowData(rw.stagedFiles))

    rw.selectRef("refs/stash")
    assert rw.committedFiles.isVisibleTo(rw)
    assert qlvGetRowData(rw.committedFiles) == stashedFiles


def testNewStashWithoutIdentity(tempDir, mainWindow):
    wd = unpackRepo(tempDir, userName="", userEmail="")
    writeFile(F"{wd}/a/untracked.txt", "this file is untracked\n")  # unstaged change
    rw = mainWindow.openRepo(wd)
    sb = rw.sidebar
    repo = rw.repo

    node = next(sb.findNodesByKind(EItem.StashesHeader))
    menu = sb.makeNodeMenu(node)
    triggerMenuAction(menu, "stash changes")

    dlg: StashDialog = findQDialog(rw, "new stash")
    dlg.ui.messageEdit.setText("helloworld")
    dlg.accept()

    assert not os.path.isfile(f"{wd}/a/untracked.txt")
    assert len(repo.listall_stashes()) == 1
    assert "helloworld" == sb.findNodeByRef("stash@{0}").createIndex(sb.sidebarModel).data(Qt.ItemDataRole.DisplayRole)
    assert qlvGetRowData(rw.dirtyFiles) == []


def testNewStashNothingToStash(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)

    node = next(rw.sidebar.findNodesByKind(EItem.StashesHeader))
    menu = rw.sidebar.makeNodeMenu(node)
    triggerMenuAction(menu, "stash changes")

    acceptQMessageBox(rw, "no.+changes to stash")


def testNewStashCantStashSubmodule(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    submoAbsPath, submoCommit = reposcenario.submodule(wd)
    writeFile(f"{submoAbsPath}/dirty.txt", "coucou")
    rw = mainWindow.openRepo(wd)

    node = next(rw.sidebar.findNodesByKind(EItem.StashesHeader))
    menu = rw.sidebar.makeNodeMenu(node)
    triggerMenuAction(menu, "stash changes")

    acceptQMessageBox(rw, "no.+changes to stash.+submodules cannot be stashed")


def testPopStash(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    reposcenario.stashedChange(wd)
    rw = mainWindow.openRepo(wd)
    repo = rw.repo

    assert 1 == len(list(rw.sidebar.findNodesByKind(EItem.Stash)))
    node = rw.sidebar.findNodeByRef("stash@{0}")
    menu = rw.sidebar.makeNodeMenu(node)
    triggerMenuAction(menu, "^apply")

    qmb = findQMessageBox(rw, "apply.*stash")
    assert "delete" in qmb.checkBox().text().lower()
    qmb.checkBox().setChecked(True)
    qmb.accept()

    assert 0 == len(repo.listall_stashes())
    assert [] == list(rw.sidebar.findNodesByKind(EItem.Stash))
    assert qlvGetRowData(rw.dirtyFiles) == ["a/a1.txt"]


def testApplyStash(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    reposcenario.stashedChange(wd)
    rw = mainWindow.openRepo(wd)
    repo = rw.repo

    assert 1 == len(list(rw.sidebar.findNodesByKind(EItem.Stash)))
    node = rw.sidebar.findNodeByRef("stash@{0}")
    menu = rw.sidebar.makeNodeMenu(node)
    triggerMenuAction(menu, r"^apply")

    qmb = findQMessageBox(rw, "apply.*stash")
    assert "delete" in qmb.checkBox().text().lower()
    qmb.checkBox().setChecked(False)
    qmb.accept()

    assert 1 == len(repo.listall_stashes())
    assert 1 == len(list(rw.sidebar.findNodesByKind(EItem.Stash)))
    assert qlvGetRowData(rw.dirtyFiles) == ["a/a1.txt"]


def testDropStash(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    reposcenario.stashedChange(wd)
    rw = mainWindow.openRepo(wd)
    repo = rw.repo

    assert qlvGetRowData(rw.dirtyFiles) == []

    assert 1 == len(list(rw.sidebar.findNodesByKind(EItem.Stash)))
    node = rw.sidebar.findNodeByRef("stash@{0}")
    menu = rw.sidebar.makeNodeMenu(node)
    triggerMenuAction(menu, "^delete")

    acceptQMessageBox(rw, "really delete.+stash")

    assert 0 == len(repo.listall_stashes())
    assert 0 == len(list(rw.sidebar.findNodesByKind(EItem.Stash)))
    assert qlvGetRowData(rw.dirtyFiles) == []


def testHideStash(tempDir, mainWindow):
    wd = unpackRepo(tempDir)

    with RepoContext(wd) as repo:
        touchFile(f"{wd}/stashthis.txt")
        stashOid = repo.create_stash("purr", ["stashthis.txt"])

    rw = mainWindow.openRepo(wd)
    assert stashOid.hex not in rw.state.uiPrefs.hiddenStashCommits
    rw.graphView.selectCommit(stashOid, silent=False)  # must not raise

    node = rw.sidebar.findNodeByRef("stash@{0}")
    menu = rw.sidebar.makeNodeMenu(node)
    triggerMenuAction(menu, "^hide")

    assert stashOid.hex in rw.state.uiPrefs.hiddenStashCommits
    with pytest.raises(Exception):
        rw.graphView.selectCommit(stashOid, silent=False)


def testDropHiddenStash(tempDir, mainWindow):
    wd = unpackRepo(tempDir)

    with RepoContext(wd) as repo:
        touchFile(f"{wd}/stashthis.txt")
        stashOid = repo.create_stash("purr", ["stashthis.txt"])

    rw = mainWindow.openRepo(wd)
    rw.toggleHideStash(stashOid)
    assert stashOid.hex in rw.state.uiPrefs.hiddenStashCommits
    DropStash.invoke(rw, stashOid)
    acceptQMessageBox(rw, "really delete.+stash")
    assert stashOid.hex not in rw.state.uiPrefs.hiddenStashCommits


def testApplyStashWithConflicts(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    reposcenario.stashedChange(wd)
    writeFile(f"{wd}/a/a1.txt", "a1\nCONFLICTING CHANGE\n")
    rw = mainWindow.openRepo(wd)
    repo = rw.repo

    node = rw.sidebar.findNodeByRef("stash@{0}")
    menu = rw.sidebar.makeNodeMenu(node)
    triggerMenuAction(menu, r"^apply")
    acceptQMessageBox(rw, "apply.+stash")

    acceptQMessageBox(rw, "conflict.+working dir")

    repo.index.add_all()
    repo.create_commit_on_head("conflicting thing", TEST_SIGNATURE, TEST_SIGNATURE)
    rw.refreshRepo()

    node = rw.sidebar.findNodeByRef("stash@{0}")
    menu = rw.sidebar.makeNodeMenu(node)
    triggerMenuAction(menu, r"^apply")
    acceptQMessageBox(rw, "apply.+stash")

    acceptQMessageBox(rw, "has caused merge conflicts")
    assert rw.sidebar.findNodeByRef("stash@{0}")  # stash not deleted
    rw.dirtyFiles.selectFile("a/a1.txt")
    assert rw.conflictView.isVisibleTo(rw)
    assert rw.conflictView.currentConflict.ours.path == "a/a1.txt"
