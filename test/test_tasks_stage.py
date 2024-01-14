from . import reposcenario
from .util import *


def testStageEmptyUntrackedFile(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    touchFile(F"{wd}/SomeNewFile.txt")
    rw = mainWindow.openRepo(wd)

    assert qlvGetRowData(rw.dirtyFiles) == ["SomeNewFile.txt"]
    assert qlvGetRowData(rw.stagedFiles) == []

    qlvClickNthRow(rw.dirtyFiles, 0)
    qtbot.keyPress(rw.dirtyFiles, Qt.Key.Key_Return)

    assert qlvGetRowData(rw.dirtyFiles) == []
    assert qlvGetRowData(rw.stagedFiles) == ["SomeNewFile.txt"]
    assert rw.repo.status() == {"SomeNewFile.txt": GIT_STATUS_INDEX_NEW}


def testDiscardUntrackedFile(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    touchFile(F"{wd}/SomeNewFile.txt")
    rw = mainWindow.openRepo(wd)

    assert qlvGetRowData(rw.dirtyFiles) == ["SomeNewFile.txt"]
    qlvClickNthRow(rw.dirtyFiles, 0)
    qtbot.keyPress(rw.dirtyFiles, Qt.Key.Key_Delete)

    acceptQMessageBox(rw, "really delete")

    assert rw.dirtyFiles.model().rowCount() == 0
    assert rw.stagedFiles.model().rowCount() == 0
    assert rw.repo.status() == {}


def testDiscardUnstagedFileModification(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    writeFile(F"{wd}/a/a1.txt", "a1\nPENDING CHANGE\n")  # unstaged change
    rw = mainWindow.openRepo(wd)

    assert qlvGetRowData(rw.dirtyFiles) == ["a/a1.txt"]
    assert qlvGetRowData(rw.stagedFiles) == []
    qlvClickNthRow(rw.dirtyFiles, 0)
    qtbot.keyPress(rw.dirtyFiles, Qt.Key.Key_Delete)

    acceptQMessageBox(rw, "really discard changes")

    assert qlvGetRowData(rw.dirtyFiles) == []
    assert qlvGetRowData(rw.stagedFiles) == []
    assert rw.repo.status() == {}


def testDiscardFileModificationWithoutAffectingStagedChange(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    reposcenario.fileWithStagedAndUnstagedChanges(wd)
    rw = mainWindow.openRepo(wd)

    assert qlvGetRowData(rw.dirtyFiles) == ["a/a1.txt"]
    assert qlvGetRowData(rw.stagedFiles) == ["a/a1.txt"]
    qlvClickNthRow(rw.dirtyFiles, 0)
    qtbot.keyPress(rw.dirtyFiles, Qt.Key.Key_Delete)

    acceptQMessageBox(rw, "really discard changes")

    assert qlvGetRowData(rw.dirtyFiles) == []
    assert qlvGetRowData(rw.stagedFiles) == ["a/a1.txt"]
    assert rw.repo.status() == {"a/a1.txt": GIT_STATUS_INDEX_MODIFIED}


def testDiscardModeChange(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    path = f"{wd}/a/a1.txt"
    assert os.lstat(path).st_mode & 0o777 == 0o644

    writeFile(path, "keep this!")
    os.chmod(path, 0o777)

    rw = mainWindow.openRepo(wd)
    assert qlvGetRowData(rw.dirtyFiles) == ["[+x] a/a1.txt"]
    qlvClickNthRow(rw.dirtyFiles, 0)
    contextMenu = rw.dirtyFiles.makeContextMenu()
    findMenuAction(contextMenu, "(restore|revert|discard) mode").trigger()
    acceptQMessageBox(rw, "(restore|revert|discard) mode")

    assert readFile(path).decode() == "keep this!"
    assert os.lstat(path).st_mode & 0o777 == 0o644


def testUnstageChangeInEmptyRepo(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir, "TestEmptyRepository")
    reposcenario.stagedNewEmptyFile(wd)
    rw = mainWindow.openRepo(wd)

    assert qlvGetRowData(rw.dirtyFiles) == []
    assert qlvGetRowData(rw.stagedFiles) == ["SomeNewFile.txt"]
    qlvClickNthRow(rw.stagedFiles, 0)
    qtbot.keyPress(rw.stagedFiles, Qt.Key.Key_Delete)

    assert qlvGetRowData(rw.dirtyFiles) == ["SomeNewFile.txt"]
    assert qlvGetRowData(rw.stagedFiles) == []

    assert rw.repo.status() == {"SomeNewFile.txt": GIT_STATUS_WT_NEW}
