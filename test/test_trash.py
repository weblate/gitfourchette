from . import reposcenario
from .fixtures import *
from .util import *
from gitfourchette.trash import Trash


def testBackupDiscardedPatches(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)

    from gitfourchette import settings

    os.unlink(F"{wd}/a/a2.txt")
    writeFile(F"{wd}/a/a1.txt", "a1\nPENDING CHANGE\n")
    writeFile(F"{wd}/SomeNewFile.txt", "this file is untracked")
    writeFile(F"{wd}/MassiveFile.txt", "." * (1024 * settings.prefs.trash_maxFileSizeKB + 1))

    rw.quickRefresh()  # refresh manually because we added files after repowidget was already created

    assert set(qlvGetRowData(rw.dirtyFiles)) == {"a/a1.txt", "a/a2.txt", "MassiveFile.txt", "SomeNewFile.txt"}
    assert qlvGetRowData(rw.stagedFiles) == []

    trash = Trash(rw.repo)
    assert len(trash.trashFiles) == 0

    QTest.keySequence(rw.dirtyFiles, QKeySequence("Ctrl+A,Del"))
    acceptQMessageBox(rw, "really discard changes")

    trash.refreshFiles()
    assert len(trash.trashFiles) == 2
    assert any("a1.txt" in f for f in trash.trashFiles)
    assert any("SomeNewFile.txt" in f for f in trash.trashFiles)
    assert not any("a2.txt" in f for f in trash.trashFiles)  # file deletions shouldn't be backed up
    assert not any("MassiveFile.txt" in f for f in trash.trashFiles)  # file is too large to be backed up


def testTrashFull(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    writeFile(F"{wd}/a/a1.txt", "a1\nPENDING CHANGE\n")  # unstaged change
    rw = mainWindow.openRepo(wd)

    from gitfourchette import settings

    # Create N junk files in trash
    N = settings.prefs.trash_maxFiles * 2
    trash = Trash(rw.repo)
    os.makedirs(trash.trashDir, exist_ok=True)
    for i in range(N):
        with open(F"{trash.trashDir}/19991231T235900-test{i}.txt", "w") as junk:
            junk.write(F"test{i}")

    qlvClickNthRow(rw.dirtyFiles, 0)
    QTest.keyPress(rw.dirtyFiles, Qt.Key_Delete)
    acceptQMessageBox(rw, "really discard changes")

    # Trash should have been purged to make room for new patch
    trash = Trash(rw.repo)
    assert len(trash.trashFiles) == settings.prefs.trash_maxFiles
    assert "a1.txt" in trash.trashFiles[0]
