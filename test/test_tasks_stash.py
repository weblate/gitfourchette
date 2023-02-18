from . import reposcenario
from .fixtures import *
from .util import *
from gitfourchette.widgets.sidebar import EItem
from gitfourchette.widgets.stashdialog import StashDialog


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


def testPopStash(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    reposcenario.stashedChange(wd)
    rw = mainWindow.openRepo(wd)
    repo = rw.repo

    stashDatas = rw.sidebar.datasForItemType(EItem.Stash)
    assert len(stashDatas) == 1

    menu = rw.sidebar.generateMenuForEntry(EItem.Stash, stashDatas[0])
    findMenuAction(menu, "^pop").trigger()

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


