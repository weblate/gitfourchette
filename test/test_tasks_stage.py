import pytest

from . import reposcenario
from .util import *


def doStage(rw, method):
    if method == "key":
        QTest.keyPress(rw.dirtyFiles, Qt.Key.Key_Return)
    elif method == "menu":
        triggerMenuAction(rw.dirtyFiles.makeContextMenu(), "stage")
    elif method == "button":
        rw.stageButton.click()
    else:
        raise NotImplementedError("unknown method")


def doDiscard(rw, method):
    if method == "key":
        QTest.keyPress(rw.dirtyFiles, Qt.Key.Key_Delete)
    elif method == "menu":
        triggerMenuAction(rw.dirtyFiles.makeContextMenu(), "discard")
    elif method == "button":
        triggerMenuAction(rw.stageButton.menu(), "discard")
    else:
        raise NotImplementedError("unknown method")


def doUnstage(rw, method):
    if method == "key":
        QTest.keyPress(rw.stagedFiles, Qt.Key.Key_Delete)
    elif method == "menu":
        triggerMenuAction(rw.stagedFiles.makeContextMenu(), "unstage")
    elif method == "button":
        rw.unstageButton.click()
    else:
        raise NotImplementedError("unknown method")


@pytest.mark.parametrize("method", ["key", "menu", "button"])
def testStageEmptyUntrackedFile(tempDir, mainWindow, method):
    wd = unpackRepo(tempDir)
    touchFile(F"{wd}/SomeNewFile.txt")
    rw = mainWindow.openRepo(wd)

    assert qlvGetRowData(rw.dirtyFiles) == ["SomeNewFile.txt"]
    assert qlvGetRowData(rw.stagedFiles) == []

    qlvClickNthRow(rw.dirtyFiles, 0)
    doStage(rw, method)

    assert qlvGetRowData(rw.dirtyFiles) == []
    assert qlvGetRowData(rw.stagedFiles) == ["SomeNewFile.txt"]
    assert rw.repo.status() == {"SomeNewFile.txt": FileStatus.INDEX_NEW}


@pytest.mark.parametrize("method", ["key", "menu", "button"])
def testDiscardUntrackedFile(tempDir, mainWindow, method):
    wd = unpackRepo(tempDir)
    touchFile(F"{wd}/SomeNewFile.txt")
    rw = mainWindow.openRepo(wd)

    assert qlvGetRowData(rw.dirtyFiles) == ["SomeNewFile.txt"]

    qlvClickNthRow(rw.dirtyFiles, 0)
    doDiscard(rw, method)
    acceptQMessageBox(rw, "really delete")

    assert rw.dirtyFiles.model().rowCount() == 0
    assert rw.stagedFiles.model().rowCount() == 0
    assert rw.repo.status() == {}


@pytest.mark.parametrize("method", ["key", "menu", "button"])
def testDiscardUnstagedFileModification(tempDir, mainWindow, method):
    wd = unpackRepo(tempDir)
    writeFile(F"{wd}/a/a1.txt", "a1\nPENDING CHANGE\n")  # unstaged change
    rw = mainWindow.openRepo(wd)

    assert qlvGetRowData(rw.dirtyFiles) == ["a/a1.txt"]
    assert qlvGetRowData(rw.stagedFiles) == []
    qlvClickNthRow(rw.dirtyFiles, 0)

    doDiscard(rw, method)
    acceptQMessageBox(rw, "really discard changes")

    assert qlvGetRowData(rw.dirtyFiles) == []
    assert qlvGetRowData(rw.stagedFiles) == []
    assert rw.repo.status() == {}


@pytest.mark.parametrize("method", ["key", "menu", "button"])
def testDiscardFileModificationWithoutAffectingStagedChange(tempDir, mainWindow, method):
    wd = unpackRepo(tempDir)
    reposcenario.fileWithStagedAndUnstagedChanges(wd)
    rw = mainWindow.openRepo(wd)

    assert qlvGetRowData(rw.dirtyFiles) == ["a/a1.txt"]
    assert qlvGetRowData(rw.stagedFiles) == ["a/a1.txt"]
    qlvClickNthRow(rw.dirtyFiles, 0)

    doDiscard(rw, method)
    acceptQMessageBox(rw, "really discard changes")

    assert qlvGetRowData(rw.dirtyFiles) == []
    assert qlvGetRowData(rw.stagedFiles) == ["a/a1.txt"]
    assert rw.repo.status() == {"a/a1.txt": FileStatus.INDEX_MODIFIED}


def testDiscardModeChange(tempDir, mainWindow):
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


@pytest.mark.parametrize("method", ["key", "menu", "button"])
def testUnstageChangeInEmptyRepo(tempDir, mainWindow, method):
    wd = unpackRepo(tempDir, "TestEmptyRepository")
    reposcenario.stagedNewEmptyFile(wd)
    rw = mainWindow.openRepo(wd)

    assert qlvGetRowData(rw.dirtyFiles) == []
    assert qlvGetRowData(rw.stagedFiles) == ["SomeNewFile.txt"]
    qlvClickNthRow(rw.stagedFiles, 0)

    doUnstage(rw, method)

    assert qlvGetRowData(rw.dirtyFiles) == ["SomeNewFile.txt"]
    assert qlvGetRowData(rw.stagedFiles) == []

    assert rw.repo.status() == {"SomeNewFile.txt": FileStatus.WT_NEW}
