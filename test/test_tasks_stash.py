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

    assert len(rw.sidebar.indicesForItemType(EItem.Stash)) == 0
    assert qlvGetRowData(rw.dirtyFiles) == ["a/a1.txt"]

    menu = rw.sidebar.generateMenuForEntry(EItem.StashesHeader)
    findMenuAction(menu, "new stash").trigger()

    dlg: StashDialog = findQDialog(rw, "new stash")
    dlg.ui.messageEdit.setText("helloworld")
    dlg.accept()

    stashIndices = rw.sidebar.indicesForItemType(EItem.Stash)
    assert len(repo.listall_stashes()) == 1
    assert len(stashIndices) == 1
    assert stashIndices[0].data(Qt.DisplayRole).endswith("helloworld")
    assert qlvGetRowData(rw.dirtyFiles) == []


def testPopStash(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    reposcenario.stashedChange(wd)
    rw = mainWindow.openRepo(wd)
    repo = rw.repo

    stashIndices = rw.sidebar.indicesForItemType(EItem.Stash)
    assert len(stashIndices) == 1

    menu = rw.sidebar.generateMenuForEntry(EItem.Stash, stashIndices[0].data(Qt.UserRole))
    findMenuAction(menu, "^pop").trigger()

    stashIndices = rw.sidebar.indicesForItemType(EItem.Stash)
    assert len(repo.listall_stashes()) == 0
    assert len(stashIndices) == 0
    assert qlvGetRowData(rw.dirtyFiles) == ["a/a1.txt"]


def testApplyStash(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    reposcenario.stashedChange(wd)
    rw = mainWindow.openRepo(wd)
    repo = rw.repo

    stashIndices = rw.sidebar.indicesForItemType(EItem.Stash)
    assert len(stashIndices) == 1

    menu = rw.sidebar.generateMenuForEntry(EItem.Stash, stashIndices[0].data(Qt.UserRole))
    findMenuAction(menu, r"^apply").trigger()

    stashIndices = rw.sidebar.indicesForItemType(EItem.Stash)
    assert len(repo.listall_stashes()) == 1
    assert len(stashIndices) == 1
    assert qlvGetRowData(rw.dirtyFiles) == ["a/a1.txt"]


def testDropStash(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    reposcenario.stashedChange(wd)
    rw = mainWindow.openRepo(wd)
    repo = rw.repo

    assert qlvGetRowData(rw.dirtyFiles) == []

    stashIndices = rw.sidebar.indicesForItemType(EItem.Stash)
    assert len(stashIndices) == 1

    menu = rw.sidebar.generateMenuForEntry(EItem.Stash, stashIndices[0].data(Qt.UserRole))
    findMenuAction(menu, "^delete").trigger()

    acceptQMessageBox(rw, "really delete.+stash")

    stashIndices = rw.sidebar.indicesForItemType(EItem.Stash)
    assert len(repo.listall_stashes()) == 0
    assert len(stashIndices) == 0
    assert qlvGetRowData(rw.dirtyFiles) == []


