from . import reposcenario
from .fixtures import *
from .util import *
from gitfourchette import porcelain
from gitfourchette.nav import NavLocator
from gitfourchette.diffview.diffview import DiffView
import pygit2


def testSensibleMessageShownForUnstagedEmptyFile(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    touchFile(F"{wd}/NewEmptyFile.txt")
    rw = mainWindow.openRepo(wd)

    qlvClickNthRow(rw.dirtyFiles, 0)

    assert not rw.diffView.isVisibleTo(rw)
    assert rw.specialDiffView.isVisibleTo(rw)
    assert "empty" in rw.specialDiffView.toPlainText().lower()


def testStagePartialPatchInUntrackedFile(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    writeFile(F"{wd}/NewFile.txt", "line A\nline B\nline C\n")
    rw = mainWindow.openRepo(wd)

    qlvClickNthRow(rw.dirtyFiles, 0)
    assert rw.repo.status() == {"NewFile.txt": pygit2.GIT_STATUS_WT_NEW}

    rw.diffView.setFocus()
    QTest.keyPress(rw.diffView, Qt.Key_Return)

    assert rw.repo.status() == {"NewFile.txt": pygit2.GIT_STATUS_INDEX_NEW | pygit2.GIT_STATUS_WT_MODIFIED}

    stagedId = rw.repo.index["NewFile.txt"].id
    stagedBlob: pygit2.Blob = rw.repo[stagedId].peel(pygit2.Blob)
    assert stagedBlob.data == b"line A\n"


def testPartialPatchSpacesInFilename(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    writeFile(F"{wd}/file with spaces.txt", "line A\nline B\nline C\n")
    rw = mainWindow.openRepo(wd)

    qlvClickNthRow(rw.dirtyFiles, 0)
    assert rw.repo.status() == {"file with spaces.txt": pygit2.GIT_STATUS_WT_NEW}

    rw.diffView.setFocus()
    QTest.keyPress(rw.diffView, Qt.Key_Return)

    assert rw.repo.status() == {"file with spaces.txt": pygit2.GIT_STATUS_INDEX_NEW | pygit2.GIT_STATUS_WT_MODIFIED}

    stagedId = rw.repo.index["file with spaces.txt"].id
    stagedBlob: pygit2.Blob = rw.repo[stagedId].peel(pygit2.Blob)
    assert stagedBlob.data == b"line A\n"


def testPartialPatchPreservesExecutableFileMode(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)

    with RepositoryContextManager(wd) as repo:
        os.chmod(F"{wd}/master.txt", 0o755)
        repo.index.add_all(["master.txt"])
        porcelain.createCommit(repo, "master.txt +x", TEST_SIGNATURE, TEST_SIGNATURE)

    writeFile(F"{wd}/master.txt", "This file is +x now\nOn master\nOn master\nDon't stage this line\n")

    rw = mainWindow.openRepo(wd)
    assert rw.repo.status() == {"master.txt": pygit2.GIT_STATUS_WT_MODIFIED}

    # Partial patch of first modified line
    qlvClickNthRow(rw.dirtyFiles, 0)
    rw.diffView.setFocus()
    QTest.keyPress(rw.diffView, Qt.Key_Down)    # Skip hunk line (@@...@@)
    QTest.keyPress(rw.diffView, Qt.Key_Return)  # Stage first modified line
    assert rw.repo.status() == {"master.txt": pygit2.GIT_STATUS_WT_MODIFIED | pygit2.GIT_STATUS_INDEX_MODIFIED}

    staged: pygit2.Diff = porcelain.getStagedChanges(rw.repo, False)
    delta: pygit2.DiffDelta = next(staged.deltas)
    assert delta.new_file.path == "master.txt"
    assert delta.new_file.mode & 0o777 == 0o755

    unstaged: pygit2.Diff = porcelain.getUnstagedChanges(rw.repo, False)
    delta: pygit2.DiffDelta = next(unstaged.deltas)
    assert delta.new_file.path == "master.txt"
    assert delta.new_file.mode & 0o777 == 0o755


def testDiscardHunkNoEOL(qtbot, tempDir, mainWindow):
    NEW_CONTENTS = "change without eol"

    wd = unpackRepo(tempDir)
    writeFile(F"{wd}/master.txt", NEW_CONTENTS)
    rw = mainWindow.openRepo(wd)

    assert rw.repo.status() == {"master.txt": pygit2.GIT_STATUS_WT_MODIFIED}

    qlvClickNthRow(rw.dirtyFiles, 0)
    rw.diffView.setFocus()
    rw.diffView.discardHunk(0)

    acceptQMessageBox(rw, "discard.+hunk")
    assert NEW_CONTENTS not in readFile(f"{wd}/master.txt").decode('utf-8')


def testSubpatchNoEOL(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)

    with RepositoryContextManager(wd) as repo:
        # Commit a file WITHOUT a newline at end
        writeFile(F"{wd}/master.txt", "hello")
        repo.index.add_all(["master.txt"])
        porcelain.createCommit(repo, "no newline at end of file", TEST_SIGNATURE, TEST_SIGNATURE)

        # Add a newline to the file without committing
        writeFile(F"{wd}/master.txt", "hello\n")

    rw = mainWindow.openRepo(wd)
    assert rw.repo.status() == {"master.txt": pygit2.GIT_STATUS_WT_MODIFIED}

    # Initiate subpatch by selecting lines and hitting return
    qlvClickNthRow(rw.dirtyFiles, 0)
    rw.diffView.setFocus()
    rw.diffView.selectAll()
    QTest.keyPress(rw.diffView, Qt.Key.Key_Return)
    assert rw.repo.status() == {"master.txt": pygit2.GIT_STATUS_INDEX_MODIFIED}

    # It must also work in reverse - let's unstage this change via a subpatch
    qlvClickNthRow(rw.stagedFiles, 0)
    rw.diffView.setFocus()
    rw.diffView.selectAll()
    QTest.keyPress(rw.diffView, Qt.Key.Key_Delete)
    assert rw.repo.status() == {"master.txt": pygit2.GIT_STATUS_WT_MODIFIED}

    # Finally, let's discard this change via a subpatch
    qlvClickNthRow(rw.dirtyFiles, 0)
    rw.diffView.setFocus()
    rw.diffView.selectAll()
    QTest.keyPress(rw.diffView, Qt.Key.Key_Delete)
    acceptQMessageBox(rw, "discard")
    assert rw.repo.status() == {}


def testDiffInNewWindow(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    assert 1 == len(QGuiApplication.topLevelWindows())

    oid = pygit2.Oid(hex='1203b03dc816ccbb67773f28b3c19318654b0bc8')
    rw.graphView.selectCommit(oid)
    qlvClickNthRow(rw.committedFiles, 0)
    assert rw.navLocator.isSimilarEnoughTo(NavLocator.inCommit(oid, "c/c2.txt"))

    rw.committedFiles.openDiffInNewWindow.emit(rw.diffView.currentPatch, rw.navLocator)

    assert 2 == len(QGuiApplication.topLevelWindows())
    diffWidget = next(w for w in QApplication.topLevelWidgets() if isinstance(w, DiffView))
    assert diffWidget.isWindow()
    assert diffWidget.window() is not mainWindow
    assert diffWidget.window() is diffWidget
    assert "c2.txt" in diffWidget.windowTitle()

    # Make sure the diff is closed when the repowidget is gone
    mainWindow.closeAllTabs()
    qtbot.wait(1)  # doesn't get a chance to clean up windows without this...
    assert 1 == len(QGuiApplication.topLevelWindows())
