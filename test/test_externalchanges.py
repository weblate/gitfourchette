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

    rw.refreshRepo()
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


def testPatchBecameInvalid(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)

    writeFile(f"{wd}/a/a2.txt", "change a\nchange b\nchange c\n")
    writeFile(f"{wd}/b/b2.txt", "change a\nchange b\nchange c\n")

    rw = mainWindow.openRepo(wd)

    assert qlvGetRowData(rw.dirtyFiles) == ["a/a2.txt", "b/b2.txt"]

    writeFile(f"{wd}/b/b2.txt", "pulled the rug out from under the cached patch")
    qlvClickNthRow(rw.dirtyFiles, 1)  # Select b/b2.txt

    assert not rw.diffView.isVisibleTo(rw)
    assert rw.richDiffView.isVisibleTo(rw)
    doc = rw.richDiffView.document()
    text = doc.toRawText()
    assert "changed on disk" in text.lower()


