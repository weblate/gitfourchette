from . import reposcenario
from .fixtures import *
from .util import *
from gitfourchette.widgets.repowidget import RepoWidget
from gitfourchette.widgets.remotedialog import RemoteDialog
from gitfourchette.widgets.sidebar import EItem
from gitfourchette.widgets.stashdialog import StashDialog
from gitfourchette import porcelain
import re
import shutil
import subprocess
import threading


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


def testHiddenBranchGotDeleted(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)

    subprocess.run(["git", "branch", "master2", "master"], check=True, cwd=wd)

    rw = mainWindow.openRepo(wd)
    rw.toggleHideBranch("refs/heads/master2")
    rw.state.uiPrefs.write(force=True)
    mainWindow.closeCurrentTab()

    subprocess.run(["git", "branch", "-D", "master2"], check=True, cwd=wd)

    mainWindow.openRepo(wd)  # reopening the repo must not crash


def testStayOnFileAfterPartialPatchDespiteExternalChange(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)

    writeFile(f"{wd}/a/a2.txt", "change a\nchange b\nchange c\n")
    writeFile(f"{wd}/b/b2.txt", "change a\nchange b\nchange c\n")
    writeFile(f"{wd}/c/c1.txt", "change a\nchange b\nchange c\n")

    rw = mainWindow.openRepo(wd)

    assert qlvGetRowData(rw.dirtyFiles) == ["a/a2.txt", "b/b2.txt", "c/c1.txt"]

    # Create a new change to a file that comes before b2.txt alphabetically
    writeFile(f"{wd}/a/a1.txt", "change a\nchange b\nchange c\n")

    # Stage a single line
    qlvClickNthRow(rw.dirtyFiles, 1)
    rw.diffView.setFocus()
    QTest.keyPress(rw.diffView, Qt.Key_Return)

    # This was a partial patch, so b2 is both dirty and staged;
    # also, a1 should appear among the dirty files now
    assert qlvGetRowData(rw.dirtyFiles) == ["a/a1.txt", "a/a2.txt", "b/b2.txt", "c/c1.txt"]
    assert qlvGetRowData(rw.stagedFiles) == ["b/b2.txt"]

    # Ensure we're still selecting b2.txt despite a1.txt appearing before us in the list
    assert qlvGetSelection(rw.dirtyFiles) == ["b/b2.txt"]


def testFSWDetectsNewFile(qtbot, mainWindow, tempDir):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    rw.installFileWatcher(0)  # boot FSW

    # we're starting clean
    assert qlvGetRowData(rw.dirtyFiles) == []

    writeFile(F"{wd}/SomeNewFile.txt", "gotta see this change without manually refreshing...\n")

    qtbot.waitSignal(rw.fileWatcher.directoryChanged).wait()

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

    qtbot.waitSignal(rw.fileWatcher.directoryChanged).wait()

    # we must see the change
    assert qlvGetRowData(rw.dirtyFiles) == ["master.txt"]


def testFSWDetectsFileDeletion(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    rw.installFileWatcher(0)  # boot FSW

    # we're starting clean
    assert qlvGetRowData(rw.dirtyFiles) == []

    os.unlink(F"{wd}/c/c1.txt")

    qtbot.waitSignal(rw.fileWatcher.directoryChanged).wait()

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

    qtbot.waitSignal(rw.fileWatcher.directoryChanged).wait()

    # we must see the change
    assert qlvGetRowData(rw.dirtyFiles) == ["c/c1.txt"]


def testFSWDetectsNestedFolderDeletion(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)

    os.mkdir(F"{wd}/c/x")
    os.mkdir(F"{wd}/c/x/y")
    touchFile(F"{wd}/c/x/y/z.txt")

    # Create a directory that starts with the same prefix as the directory we're going to delete ("c")
    # to ensure that it doesn't get swept up with "c" when "c" and its subdirectories get unwatched.
    os.mkdir(F"{wd}/c-keepwatching")
    touchFile(F"{wd}/c-keepwatching/keepwatchingme.txt")

    rw = mainWindow.openRepo(wd)
    rw.installFileWatcher(0)  # boot FSW

    assert set(qlvGetRowData(rw.dirtyFiles)) == {"c/x/y/z.txt", "c-keepwatching/keepwatchingme.txt"}

    # Delete "c" recursively; make sure the FSW picked up the changes
    shutil.rmtree(F"{wd}/c")
    qtbot.waitSignal(rw.fileWatcher.directoryChanged).wait()
    assert set(qlvGetRowData(rw.dirtyFiles)) == {"c/c1.txt", "c-keepwatching/keepwatchingme.txt"}

    # Make sure c-keepwatching is still being watched
    touchFile(F"{wd}/c-keepwatching/watchmetoo.txt")
    qtbot.waitSignal(rw.fileWatcher.directoryChanged).wait()
    assert set(qlvGetRowData(rw.dirtyFiles)) == {"c/c1.txt", "c-keepwatching/keepwatchingme.txt", "c-keepwatching/watchmetoo.txt"}


def testFSWConcurrencyStressTest1(qtbot, tempDir, mainWindow):
    # mainWindow.show()
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    rw.installFileWatcher(0)  # boot FSW
    rw.workQueue.forceSerial = False

    for i in range(100):
        subprocess.run(F"git checkout -b master{i} --track origin/no-parent".split(" "), check=True, cwd=wd)
        with open(f"{wd}/newfile.txt", "a") as f:
            f.write(f"toto{i}")
        subprocess.run(["git", "add", f"{wd}/newfile.txt"], check=True, cwd=wd)
        subprocess.run(["git", "commit", "-m", f"newcommit{i}"], check=True, cwd=wd)
        subprocess.run(["git", "rebase", "master"], check=True, cwd=wd)
        QCoreApplication.instance().processEvents()


def testFSWConcurrencyStressTest2(qtbot, tempDir, mainWindow):
    # mainWindow.show()
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    rw.installFileWatcher(0)  # boot FSW

    class StressThread(threading.Thread):
        def __init__(self, wd):
            super().__init__()
            self.wd = wd
            self.exc = None

        def run(self):
            try:
                for i in range(1000):
                    subprocess.run(["git", "stash"], check=True, cwd=self.wd)
                    subprocess.run(["git", "stash", "pop"], check=True, cwd=self.wd)
            except BaseException as exc:
                self.exc = exc

    with open(f"{wd}/master.txt", "a") as f:
        f.write("coucou\n")
    touchFile(f"{wd}/gutenmorgen")
    subprocess.run(["git", "add", "."], check=True, cwd=wd)
    QCoreApplication.instance().processEvents()

    rw.stagedFiles.selectRow(0)
    QCoreApplication.instance().processEvents()

    rw.workQueue.forceSerial = False

    th = StressThread(wd)
    th.start()

    while th.is_alive():
        qtbot.wait(100)

    assert not th.exc


def testFSWConcurrencyStressTest3(qtbot, tempDir, mainWindow):
    # mainWindow.show()
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    rw.installFileWatcher(0)  # boot FSW

    touchFile(f"{wd}/gutenmorgen")
    subprocess.run(["git", "add", "."], check=True, cwd=wd)

    rw.workQueue.forceSerial = False

    gitLoop = subprocess.Popen(["bash", "-c", """
    set -e
    for i in $(seq 1000); do
        echo iteration $i
        git stash && git stash pop
    done
    """], cwd=wd)

    while gitLoop.poll() is None:
        qtbot.wait(100)

    assert 0 == gitLoop.returncode


def testFSWConcurrencyStressTest4(qtbot, tempDir, mainWindow):
    # mainWindow.show()
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    rw.installFileWatcher(0)  # boot FSW

    class StressThread(threading.Thread):
        def __init__(self, wd):
            super().__init__()
            self.wd = wd
            self.exc = None

        def run(self):
            try:
                for i in range(1000):
                    subprocess.run(["git", "rebase", "-i", "49322bb"], check=True, cwd=self.wd, env={"GIT_SEQUENCE_EDITOR": "true"})
            except BaseException as exc:
                self.exc = exc

    rw.stagedFiles.selectRow(0)
    QCoreApplication.instance().processEvents()

    rw.workQueue.forceSerial = False

    th = StressThread(wd)
    th.start()

    while th.is_alive():
        qtbot.wait(100)

    assert not th.exc
