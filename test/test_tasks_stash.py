from . import reposcenario
from .fixtures import *
from .util import *
from gitfourchette.widgets.sidebar import EItem
from gitfourchette.widgets.stashdialog import StashDialog
import os


def testNewStash(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    writeFile(F"{wd}/a/a1.txt", "a1\nPENDING CHANGE\n")  # unstaged change
    rw = mainWindow.openRepo(wd)
    repo = rw.repo

    assert len(repo.listall_stashes()) == 0

    assert len(rw.sidebar.datasForItemType(EItem.Stash)) == 0
    assert qlvGetRowData(rw.dirtyFiles) == ["a/a1.txt"]

    menu = rw.sidebar.generateMenuForEntry(EItem.StashesHeader)
    findMenuAction(menu, "new stash").trigger()

    dlg: StashDialog = findQDialog(rw, "new stash")
    dlg.ui.messageEdit.setText("helloworld")
    dlg.accept()

    assert len(repo.listall_stashes()) == 1
    assert ["helloworld" == rw.sidebar.datasForItemType(EItem.Stash, Qt.DisplayRole)]
    assert qlvGetRowData(rw.dirtyFiles) == []


def testNewStashWithUntrackedFiles(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    writeFile(F"{wd}/a/untracked.txt", "this file is untracked\n")  # unstaged change
    rw = mainWindow.openRepo(wd)
    repo = rw.repo

    assert len(repo.listall_stashes()) == 0

    assert len(rw.sidebar.datasForItemType(EItem.Stash)) == 0
    assert qlvGetRowData(rw.dirtyFiles) == ["a/untracked.txt"]

    menu = rw.sidebar.generateMenuForEntry(EItem.StashesHeader)
    findMenuAction(menu, "new stash").trigger()

    dlg: StashDialog = findQDialog(rw, "new stash")
    dlg.ui.messageEdit.setText("helloworld")
    dlg.ui.includeUntrackedCheckBox.setChecked(True)
    dlg.accept()

    assert not os.path.isfile(f"{wd}/a/untracked.txt")
    assert len(repo.listall_stashes()) == 1
    assert ["helloworld" == rw.sidebar.datasForItemType(EItem.Stash, Qt.DisplayRole)]
    assert qlvGetRowData(rw.dirtyFiles) == []

    rw.selectRef("refs/stash")
    assert rw.committedFiles.isVisibleTo(rw)
    assert qlvGetRowData(rw.committedFiles) == ["a/untracked.txt"]


def testNewStashWithoutIdentity(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir, userName="", userEmail="")
    writeFile(F"{wd}/a/untracked.txt", "this file is untracked\n")  # unstaged change
    rw = mainWindow.openRepo(wd)
    repo = rw.repo

    menu = rw.sidebar.generateMenuForEntry(EItem.StashesHeader)
    findMenuAction(menu, "new stash").trigger()

    dlg: StashDialog = findQDialog(rw, "new stash")
    dlg.ui.messageEdit.setText("helloworld")
    dlg.ui.includeUntrackedCheckBox.setChecked(True)
    dlg.accept()

    assert not os.path.isfile(f"{wd}/a/untracked.txt")
    assert len(repo.listall_stashes()) == 1
    assert ["helloworld" == rw.sidebar.datasForItemType(EItem.Stash, Qt.DisplayRole)]
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


