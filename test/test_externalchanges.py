import subprocess

from . import reposcenario
from .fixtures import *
from .util import *
from gitfourchette.widgets.repowidget import RepoWidget
from gitfourchette.widgets.remotedialog import RemoteDialog
from gitfourchette.widgets.sidebar import EItem
from gitfourchette.widgets.stashdialog import StashDialog
from gitfourchette import porcelain
import re


def testExternalUnstage(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    writeFile(F"{wd}/master.txt", "same old file -- brand new contents!\n")

    rw = mainWindow.openRepo(wd)
    repo = rw.repo

    # Stage master.txt
    assert (qlvGetRowData(rw.dirtyFiles), qlvGetRowData(rw.stagedFiles)) == (["master.txt"], [])
    qlvClickNthRow(rw.dirtyFiles, 0)
    QTest.keyPress(rw.dirtyFiles, Qt.Key_Return)
    assert (qlvGetRowData(rw.dirtyFiles), qlvGetRowData(rw.stagedFiles)) == ([], ["master.txt"])

    # Unstage master.txt with git itself, outside of GF
    externalGitUnstageCmd = ["git", "restore", "--staged", "master.txt"]

    subprocess.run(externalGitUnstageCmd, check=True, cwd=wd)

    rw.quickRefresh()
    assert (qlvGetRowData(rw.dirtyFiles), qlvGetRowData(rw.stagedFiles)) == (["master.txt"], [])


def testFSWDetectsNewFile(qtbot, mainWindow, tempDir):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    rw.installFileWatcher(0)  # boot FSW

    # we're starting clean
    assert qlvGetRowData(rw.dirtyFiles) == []

    writeFile(F"{wd}/SomeNewFile.txt", "gotta see this change without manually refreshing...\n")
    qtbot.wait(500)

    # we must see the change
    assert qlvGetRowData(rw.dirtyFiles) == ["SomeNewFile.txt"]


def testFSWDetectsChangedFile(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    rw.installFileWatcher(0)  # boot FSW

    # we're starting clean
    assert qlvGetRowData(rw.dirtyFiles) == []

    writeFile(F"{wd}/master.txt", "gotta see this change without manually refreshing...\n")

    # gotta do this for the FSW to pick up modifications to existing files in a unit testing environment.
    touchFile(F"{wd}/master.txt")

    qtbot.wait(500)

    # we must see the change
    assert qlvGetRowData(rw.dirtyFiles) == ["master.txt"]


def testFSWDetectsFileDeletion(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    rw.installFileWatcher(0)  # boot FSW

    # we're starting clean
    assert qlvGetRowData(rw.dirtyFiles) == []

    os.unlink(F"{wd}/c/c1.txt")

    qtbot.wait(500)

    # we must see the change
    assert qlvGetRowData(rw.dirtyFiles) == ["c/c1.txt"]


def testFSWDetectsFolderDeletion(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    rw.installFileWatcher(0)  # boot FSW

    # we're starting clean
    assert qlvGetRowData(rw.dirtyFiles) == []

    os.unlink(F"{wd}/c/c1.txt")
    os.rmdir(F"{wd}/c")

    qtbot.wait(500)

    # we must see the change
    assert qlvGetRowData(rw.dirtyFiles) == ["c/c1.txt"]
