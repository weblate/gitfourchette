from . import reposcenario
from .util import *
import subprocess


def testExternalUnstage(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    writeFile(F"{wd}/master.txt", "same old file -- brand new contents!\n")

    rw = mainWindow.openRepo(wd)
    repo = rw.repo

    # Stage master.txt
    assert (qlvGetRowData(rw.dirtyFiles), qlvGetRowData(rw.stagedFiles)) == (["master.txt"], [])
    qlvClickNthRow(rw.dirtyFiles, 0)
    QTest.keyPress(rw.dirtyFiles, Qt.Key.Key_Return)
    assert (qlvGetRowData(rw.dirtyFiles), qlvGetRowData(rw.stagedFiles)) == ([], ["master.txt"])

    # Unstage master.txt with git itself, outside of GF
    externalGitUnstageCmd = ["git", "restore", "--staged", "master.txt"]

    subprocess.run(externalGitUnstageCmd, check=True, cwd=wd)

    rw.refreshRepo()
    assert (qlvGetRowData(rw.dirtyFiles), qlvGetRowData(rw.stagedFiles)) == (["master.txt"], [])


def testHiddenBranchGotDeleted(tempDir, mainWindow):
    wd = unpackRepo(tempDir)

    subprocess.run(["git", "branch", "master2", "master"], check=True, cwd=wd)

    rw = mainWindow.openRepo(wd)
    rw.toggleHideBranch("refs/heads/master2")
    rw.state.uiPrefs.write(force=True)
    mainWindow.closeCurrentTab()

    subprocess.run(["git", "branch", "-D", "master2"], check=True, cwd=wd)

    mainWindow.openRepo(wd)  # reopening the repo must not crash


def testStayOnFileAfterPartialPatchDespiteExternalChange(tempDir, mainWindow):
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
    QTest.keyPress(rw.diffView, Qt.Key.Key_Return)

    # This was a partial patch, so b2 is both dirty and staged;
    # also, a1 should appear among the dirty files now
    assert qlvGetRowData(rw.dirtyFiles) == ["a/a1.txt", "a/a2.txt", "b/b2.txt", "c/c1.txt"]
    assert qlvGetRowData(rw.stagedFiles) == ["b/b2.txt"]

    # Ensure we're still selecting b2.txt despite a1.txt appearing before us in the list
    assert qlvGetSelection(rw.dirtyFiles) == ["b/b2.txt"]


def testPatchBecameInvalid(tempDir, mainWindow):
    wd = unpackRepo(tempDir)

    writeFile(f"{wd}/a/a2.txt", "change a\nchange b\nchange c\n")
    writeFile(f"{wd}/b/b2.txt", "change a\nchange b\nchange c\n")

    rw = mainWindow.openRepo(wd)

    assert qlvGetRowData(rw.dirtyFiles) == ["a/a2.txt", "b/b2.txt"]

    qlvClickNthRow(rw.dirtyFiles, 1)  # Select b/b2.txt
    writeFile(f"{wd}/b/b2.txt", "pulled the rug out from under the cached patch")
    qlvClickNthRow(rw.dirtyFiles, 0)  # Select something else
    qlvClickNthRow(rw.dirtyFiles, 1)  # Select b/b2.txt

    assert not rw.diffView.isVisibleTo(rw)
    assert rw.specialDiffView.isVisibleTo(rw)
    doc = rw.specialDiffView.document()
    text = doc.toRawText()
    assert "changed on disk" in text.lower()


def testExternalChangeWhileTaskIsBusyThenAborts(tempDir, mainWindow):
    wd = unpackRepo(tempDir)

    rw = mainWindow.openRepo(wd)

    rw.commitButton.click()
    assert findQMessageBox(rw, r"empty commit")

    writeFile(f"{wd}/sneaky.txt", "tee hee")

    QTest.qWait(1)
    assert QGuiApplication.applicationState() == Qt.ApplicationState.ApplicationActive, "needed for onRegainForeground"

    mainWindow.onRegainForeground()
    rejectQMessageBox(rw, r"empty commit")

    # Even though the task aborts, the repo should auto-refresh
    assert qlvGetRowData(rw.dirtyFiles) == ["sneaky.txt"]
