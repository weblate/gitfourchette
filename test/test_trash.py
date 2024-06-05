from . import reposcenario
from .util import *
from gitfourchette.trash import Trash


def _fillTrashWithJunk(n):
    trash = Trash.instance()
    trash.refreshFiles()
    trash.clear()
    os.makedirs(trash.trashDir, exist_ok=True)
    for i in range(n):
        with open(F"{trash.trashDir}/19991231T235900-test{i}.txt", "w") as junk:
            junk.write(F"test{i}")
    trash.refreshFiles()


def testBackupDiscardedPatches(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    os.unlink(F"{wd}/a/a2.txt")
    writeFile(F"{wd}/a/a1.txt", "a1\nPENDING CHANGE\n")
    writeFile(F"{wd}/SomeNewFile.txt", "this file is untracked")
    writeFile(F"{wd}/MassiveFile.txt", "." * (1024 + 1))
    if not WINDOWS:
        os.symlink(f"{wd}/this/path/does/not/exist", f"{wd}/symlink")

    mainWindow.onAcceptPrefsDialog({"maxTrashFileKB": 1})
    rw = mainWindow.openRepo(wd)

    setOfDirtyFiles = {"a/a1.txt", "a/a2.txt", "MassiveFile.txt", "SomeNewFile.txt", "[link] symlink"}
    if WINDOWS:
        setOfDirtyFiles.remove("[link] symlink")
    assert set(qlvGetRowData(rw.dirtyFiles)) == setOfDirtyFiles
    assert qlvGetRowData(rw.stagedFiles) == []

    trash = Trash.instance()
    trash.refreshFiles()
    assert len(trash.trashFiles) == 0

    QTest.keySequence(rw.dirtyFiles, QKeySequence("Ctrl+A,Del"))
    acceptQMessageBox(rw, "really discard changes")

    assert len(trash.trashFiles) == 3 if not WINDOWS else 2
    assert any("a1.txt" in f for f in trash.trashFiles)
    assert any("SomeNewFile.txt" in f for f in trash.trashFiles)
    if not WINDOWS:
        assert any("symlink" in f for f in trash.trashFiles)
        assert os.path.islink(next(f for f in trash.trashFiles if "symlink" in f))
    assert not any("a2.txt" in f for f in trash.trashFiles)  # file deletions shouldn't be backed up
    assert not any("MassiveFile.txt" in f for f in trash.trashFiles)  # file is too large to be backed up


def testTrashFull(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    writeFile(F"{wd}/a/a1.txt", "a1\nPENDING CHANGE\n")  # unstaged change
    rw = mainWindow.openRepo(wd)

    from gitfourchette import settings

    # Create N junk files in trash
    _fillTrashWithJunk(settings.prefs.maxTrashFiles * 2)

    qlvClickNthRow(rw.dirtyFiles, 0)
    QTest.keyPress(rw.dirtyFiles, Qt.Key.Key_Delete)
    acceptQMessageBox(rw, "really discard changes")

    # Trash should have been purged to make room for new patch
    assert len(Trash.instance().trashFiles) == settings.prefs.maxTrashFiles
    assert "a1.txt" in Trash.instance().trashFiles[0]


def testClearTrash(mainWindow):
    assert Trash.instance().size()[1] == 0

    mainWindow.clearRescueFolder()
    acceptQMessageBox(mainWindow, "no discarded (patches|changes) to delete")

    _fillTrashWithJunk(40)
    assert Trash.instance().size()[1] == 40
    mainWindow.clearRescueFolder()
    acceptQMessageBox(mainWindow, "delete.+40.+discarded (patches|changes)")
    assert Trash.instance().size()[1] == 0
