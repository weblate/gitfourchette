from . import reposcenario
from .fixtures import *
from .util import *
from gitfourchette.sidebar.sidebarmodel import EItem
from gitfourchette.forms.stashdialog import StashDialog
import os


def testNewStash(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    writeFile(F"{wd}/a/a1.txt", "a1\nPENDING CHANGE\n")  # unstaged change
    writeFile(F"{wd}/a/untracked.txt", "this file is untracked\n")  # untracked file
    rw = mainWindow.openRepo(wd)
    repo = rw.repo

    assert len(repo.listall_stashes()) == 0

    assert len(rw.sidebar.datasForItemType(EItem.Stash)) == 0
    assert qlvGetRowData(rw.dirtyFiles) == ["a/a1.txt", "a/untracked.txt"]

    menu = rw.sidebar.generateMenuForEntry(EItem.StashesHeader)
    triggerMenuAction(menu, "stash changes")

    dlg: StashDialog = findQDialog(rw, "new stash")
    dlg.ui.messageEdit.setText("helloworld")
    dlg.accept()

    assert not os.path.isfile(f"{wd}/a/untracked.txt"), "untracked file must be gone after stashing"
    assert qlvGetRowData(rw.dirtyFiles) == [], "workdir must be clean after stashing"
    assert len(repo.listall_stashes()) == 1, "there must be one stash in the repo"
    assert ["helloworld" == rw.sidebar.datasForItemType(EItem.Stash, Qt.ItemDataRole.DisplayRole)], "stash must be in sidebar"

    rw.selectRef("refs/stash")
    assert rw.committedFiles.isVisibleTo(rw)
    assert qlvGetRowData(rw.committedFiles) == ["a/a1.txt", "a/untracked.txt"]


def testNewPartialStash(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    writeFile(F"{wd}/a/a1.txt", "a1\nPENDING CHANGE 1\n")  # unstaged change
    writeFile(F"{wd}/a/a2.txt", "a2\nPENDING CHANGE 2\n")  # unstaged change
    writeFile(F"{wd}/a/untracked1.txt", "this file is untracked 1\n")  # untracked file
    writeFile(F"{wd}/a/untracked2.txt", "this file is untracked 1\n")  # untracked file
    rw = mainWindow.openRepo(wd)
    repo = rw.repo

    dirtyFiles = ["a/a1.txt", "a/a2.txt", "a/untracked1.txt", "a/untracked2.txt"]
    stashedFiles = ["a/a2.txt", "a/untracked2.txt"]
    keptFiles = sorted(set(dirtyFiles) - set(stashedFiles))

    assert len(repo.listall_stashes()) == 0

    assert len(rw.sidebar.datasForItemType(EItem.Stash)) == 0
    assert qlvGetRowData(rw.dirtyFiles) == dirtyFiles

    menu = rw.sidebar.generateMenuForEntry(EItem.StashesHeader)
    triggerMenuAction(menu, "stash changes")

    dlg: StashDialog = findQDialog(rw, "new stash")
    dlg.ui.messageEdit.setText("helloworld")

    # Uncheck some files to produce a partial stash
    fl = dlg.ui.fileList
    assert qlvGetRowData(fl) == dirtyFiles
    for uncheckFile in keptFiles:
        qlvClickNthRow(fl, dirtyFiles.index(uncheckFile))
        fl.selectedItems()[0].setCheckState(Qt.CheckState.Unchecked)

    dlg.accept()

    assert os.path.isfile(f"{wd}/a/untracked1.txt"), "untracked file 1 should still be here"
    assert not os.path.isfile(f"{wd}/a/untracked2.txt"), "untracked file 2 must be gone"
    assert qlvGetRowData(rw.dirtyFiles) == keptFiles

    rw.selectRef("refs/stash")
    assert rw.committedFiles.isVisibleTo(rw)
    assert qlvGetRowData(rw.committedFiles) == stashedFiles


def testNewStashWithoutIdentity(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir, userName="", userEmail="")
    writeFile(F"{wd}/a/untracked.txt", "this file is untracked\n")  # unstaged change
    rw = mainWindow.openRepo(wd)
    repo = rw.repo

    menu = rw.sidebar.generateMenuForEntry(EItem.StashesHeader)
    triggerMenuAction(menu, "stash changes")

    dlg: StashDialog = findQDialog(rw, "new stash")
    dlg.ui.messageEdit.setText("helloworld")
    dlg.accept()

    assert not os.path.isfile(f"{wd}/a/untracked.txt")
    assert len(repo.listall_stashes()) == 1
    assert ["helloworld" == rw.sidebar.datasForItemType(EItem.Stash, Qt.ItemDataRole.DisplayRole)]
    assert qlvGetRowData(rw.dirtyFiles) == []


def testPopStash(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    reposcenario.stashedChange(wd)
    rw = mainWindow.openRepo(wd)
    repo = rw.repo

    stashDatas = rw.sidebar.datasForItemType(EItem.Stash)
    assert len(stashDatas) == 1

    menu = rw.sidebar.generateMenuForEntry(EItem.Stash, stashDatas[0])
    findMenuAction(menu, "^apply").trigger()

    qmb = findQMessageBox(rw, "apply.*stash")
    assert "delete" in qmb.checkBox().text().lower()
    qmb.checkBox().setChecked(True)
    qmb.accept()

    stashDatas = rw.sidebar.datasForItemType(EItem.Stash)
    assert len(repo.listall_stashes()) == 0
    assert [] == stashDatas
    assert qlvGetRowData(rw.dirtyFiles) == ["a/a1.txt"]


def testApplyStash(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    reposcenario.stashedChange(wd)
    rw = mainWindow.openRepo(wd)
    repo = rw.repo

    stashDatas = rw.sidebar.datasForItemType(EItem.Stash)
    assert len(stashDatas) == 1

    menu = rw.sidebar.generateMenuForEntry(EItem.Stash, stashDatas[0])
    findMenuAction(menu, r"^apply").trigger()

    qmb = findQMessageBox(rw, "apply.*stash")
    assert "delete" in qmb.checkBox().text().lower()
    qmb.checkBox().setChecked(False)
    qmb.accept()

    stashDatas = rw.sidebar.datasForItemType(EItem.Stash)
    assert len(repo.listall_stashes()) == 1
    assert len(stashDatas) == 1
    assert qlvGetRowData(rw.dirtyFiles) == ["a/a1.txt"]


def testDropStash(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    reposcenario.stashedChange(wd)
    rw = mainWindow.openRepo(wd)
    repo = rw.repo

    assert qlvGetRowData(rw.dirtyFiles) == []

    stashDatas = rw.sidebar.datasForItemType(EItem.Stash)
    assert len(stashDatas) == 1

    menu = rw.sidebar.generateMenuForEntry(EItem.Stash, stashDatas[0])
    findMenuAction(menu, "^delete").trigger()

    acceptQMessageBox(rw, "really delete.+stash")

    stashDatas = rw.sidebar.datasForItemType(EItem.Stash)
    assert len(repo.listall_stashes()) == 0
    assert len(stashDatas) == 0
    assert qlvGetRowData(rw.dirtyFiles) == []


