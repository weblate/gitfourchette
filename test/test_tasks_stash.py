from . import reposcenario
from .util import *
from gitfourchette.sidebar.sidebarmodel import EItem
from gitfourchette.forms.stashdialog import StashDialog
from gitfourchette.tasks import DropStash
import os
import pytest


def testNewStash(qtbot, tempDir, mainWindow):
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
    assert dlg.ui.cleanupCheckBox.isChecked()
    dlg.ui.messageEdit.setText("helloworld")
    dlg.accept()

    assert not os.path.isfile(f"{wd}/a/untracked.txt"), "untracked file must be gone after stashing"
    assert qlvGetRowData(rw.dirtyFiles) == [], "workdir must be clean after stashing"
    assert qlvGetRowData(rw.stagedFiles) == [], "workdir must be clean after stashing"
    assert len(repo.listall_stashes()) == 1, "there must be one stash in the repo"
    assert "helloworld" == sb.findNodeByRef("stash@{0}").createIndex(sb.sidebarModel).data(Qt.ItemDataRole.DisplayRole)

    rw.selectRef("refs/stash")
    assert rw.committedFiles.isVisibleTo(rw)
    assert qlvGetRowData(rw.committedFiles) == ["a/a1.txt", "a/untracked.txt", "b/b1.txt"]


def testNewPartialStash(qtbot, tempDir, mainWindow):
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

    node = next(rw.sidebar.findNodesByKind(EItem.StashesHeader))
    menu = rw.sidebar.makeNodeMenu(node)
    triggerMenuAction(menu, "stash changes")

    dlg: StashDialog = findQDialog(rw, "new stash")
    assert dlg.ui.cleanupCheckBox.isChecked()
    dlg.ui.messageEdit.setText("helloworld")

    # Uncheck some files to produce a partial stash
    fl = dlg.ui.fileList
    assert sorted(qlvGetRowData(fl)) == sorted(dirtyFiles + stagedFiles)
    for uncheckFile in keptFiles:
        i = qlvFindRow(fl, uncheckFile)
        qlvClickNthRow(fl, i)
        fl.selectedItems()[0].setCheckState(Qt.CheckState.Unchecked)

    dlg.accept()

    assert os.path.isfile(f"{wd}/a/untracked1.txt"), "untracked file 1 should still be here"
    assert not os.path.isfile(f"{wd}/a/untracked2.txt"), "untracked file 2 must be gone"
    assert keptFiles == sorted(qlvGetRowData(rw.dirtyFiles) + qlvGetRowData(rw.stagedFiles))

    rw.selectRef("refs/stash")
    assert rw.committedFiles.isVisibleTo(rw)
    assert qlvGetRowData(rw.committedFiles) == stashedFiles


def testNewStashWithoutIdentity(qtbot, tempDir, mainWindow):
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


def testPopStash(qtbot, tempDir, mainWindow):
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


def testApplyStash(qtbot, tempDir, mainWindow):
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


def testDropStash(qtbot, tempDir, mainWindow):
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


def testHideStash(qtbot, tempDir, mainWindow):
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


def testDropHiddenStash(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)

    with RepoContext(wd) as repo:
        touchFile(f"{wd}/stashthis.txt")
        stashOid = repo.create_stash("purr", ["stashthis.txt"])

    rw = mainWindow.openRepo(wd)
    rw.toggleHideStash(stashOid)
    assert stashOid.hex in rw.state.uiPrefs.hiddenStashCommits
    DropStash.invoke(stashOid)
    acceptQMessageBox(rw, "really delete.+stash")
    assert stashOid.hex not in rw.state.uiPrefs.hiddenStashCommits
