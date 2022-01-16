from PySide2.QtTest import QTest
from gitfourchette.allqt import *
from gitfourchette.dialogs.commitdialog import CommitDialog
from gitfourchette.widgets.mainwindow import MainWindow
from gitfourchette.widgets.repowidget import RepoWidget
import binascii
import os
import pygit2
import pytest
import reposcenario
import tarfile
import tempfile
import testutil


def withRepo(name):
    return pytest.mark.parametrize('testRepoName', [name])


def withPrep(fixture_name):
    return pytest.mark.parametrize('prep', [fixture_name])


@pytest.fixture
def tempDir() -> tempfile.TemporaryDirectory:
    td = tempfile.TemporaryDirectory(prefix="gitfourchettetest-")
    yield td
    td.cleanup()


@pytest.fixture
def workDir(tempDir, testRepoName, prep) -> str:
    testPath = os.path.realpath(__file__)
    testPath = os.path.dirname(testPath)

    with tarfile.open(F"{testPath}/data/{testRepoName}.tar") as tar:
        tar.extractall(tempDir.name)
    path = F"{tempDir.name}/{testRepoName}/"
    if prep:
        prep(path)
    return path


@pytest.fixture
def mainWindow() -> MainWindow:
    # Turn on test mode: Prevent loading/saving prefs; disable multithreaded work queue
    import settings
    settings.TEST_MODE = True

    mw = MainWindow()
    #mw.show()
    yield mw

    # Tear down
    mw.close()


@pytest.fixture
def rw(mainWindow, workDir) -> RepoWidget:
    return mainWindow.openRepo(workDir, addToHistory=False)


# -----------------------------------------------------------------------------


#@pytest.mark.parametrize('prep', [reposcenario.untrackedEmptyFile])
@withRepo("TestGitRepository")
@withPrep(reposcenario.untrackedEmptyFile)
def testChangedFilesShownAtStart(qtbot, rw):
    assert rw is not None
    #assert 1 == mainWindow.tabs.count()
    assert rw.graphView.model().rowCount() > 5
    assert rw.dirtyView.isVisibleTo(rw)
    assert rw.stageView.isVisibleTo(rw)
    assert not rw.changedFilesView.isVisibleTo(rw)
    assert testutil.qlvGetTextRows(rw.dirtyView) == ["SomeNewFile.txt"]
    assert testutil.qlvGetTextRows(rw.stageView) == []


@withRepo("TestGitRepository")
@withPrep(reposcenario.nestedUntrackedFiles)
def testDisplayAllNestedUntrackedFiles(qtbot, workDir, rw):
    assert testutil.qlvGetTextRows(rw.dirtyView) == ["N/tata.txt", "N/toto.txt", "N/tutu.txt"]
    assert testutil.qlvGetTextRows(rw.stageView) == []


@withRepo("TestGitRepository")
@withPrep(reposcenario.untrackedEmptyFile)
def testStageEmptyUntrackedFile(qtbot, workDir, rw):
    assert testutil.qlvGetTextRows(rw.dirtyView) == ["SomeNewFile.txt"]
    assert testutil.qlvGetTextRows(rw.stageView) == []

    testutil.qlvClickNthRow(rw.dirtyView, 0)
    QTest.keyPress(rw.dirtyView, Qt.Key_Return)
    #self.breathe()

    assert testutil.qlvGetTextRows(rw.dirtyView) == []
    assert testutil.qlvGetTextRows(rw.stageView) == ["SomeNewFile.txt"]

    repo = pygit2.Repository(workDir)
    assert repo.status() == {"SomeNewFile.txt": pygit2.GIT_STATUS_INDEX_NEW}


@withRepo("TestGitRepository")
@withPrep(reposcenario.untrackedEmptyFile)
def testDiscardUntrackedFile(qtbot, workDir, rw):
    assert testutil.qlvGetTextRows(rw.dirtyView) == ["SomeNewFile.txt"]
    testutil.qlvClickNthRow(rw.dirtyView, 0)

    QTest.keyPress(rw.dirtyView, Qt.Key_Delete)
    #self.breathe()

    qmb: QMessageBox = rw.findChild(QMessageBox)
    assert "DISCARD CHANGES" in qmb.windowTitle().upper()
    assert qmb.defaultButton() is not None
    QTest.mouseClick(qmb.defaultButton(), Qt.MouseButton.LeftButton)
    #self.breathe()

    assert rw.dirtyView.model().rowCount() == 0
    assert rw.stageView.model().rowCount() == 0

    repo = pygit2.Repository(workDir)
    assert repo.status() == {}


@withRepo("TestGitRepository")
@withPrep(reposcenario.fileWithUnstagedChange)
def testDiscardUnstagedFileModification(qtbot, workDir, rw):
    assert testutil.qlvGetTextRows(rw.dirtyView) == ["a/a1.txt"]
    assert testutil.qlvGetTextRows(rw.stageView) == []
    testutil.qlvClickNthRow(rw.dirtyView, 0)

    QTest.keyPress(rw.dirtyView, Qt.Key_Delete)
    #self.breathe()

    qmb: QMessageBox = rw.findChild(QMessageBox)
    assert "DISCARD CHANGES" in qmb.windowTitle().upper()
    assert qmb.defaultButton() is not None
    QTest.mouseClick(qmb.defaultButton(), Qt.MouseButton.LeftButton)
    #self.breathe()

    assert testutil.qlvGetTextRows(rw.dirtyView) == []
    assert testutil.qlvGetTextRows(rw.stageView) == []

    repo = pygit2.Repository(workDir)
    assert repo.status() == {}


@withRepo("TestGitRepository")
@withPrep(reposcenario.fileWithStagedAndUnstagedChanges)
def testDiscardFileModificationWithoutAffectingStagedChange(qtbot, workDir, rw):
    assert testutil.qlvGetTextRows(rw.dirtyView) == ["a/a1.txt"]
    assert testutil.qlvGetTextRows(rw.stageView) == ["a/a1.txt"]
    testutil.qlvClickNthRow(rw.dirtyView, 0)
    QTest.keyPress(rw.dirtyView, Qt.Key_Delete)
    #self.breathe()

    qmb: QMessageBox = rw.findChild(QMessageBox)
    assert "DISCARD CHANGES" in qmb.windowTitle().upper()
    assert qmb.defaultButton() is not None
    QTest.mouseClick(qmb.defaultButton(), Qt.MouseButton.LeftButton)
    #self.breathe()

    assert testutil.qlvGetTextRows(rw.dirtyView) == []
    assert testutil.qlvGetTextRows(rw.stageView) == ["a/a1.txt"]

    repo = pygit2.Repository(workDir)
    assert repo.status() == {"a/a1.txt": pygit2.GIT_STATUS_INDEX_MODIFIED}


@withRepo("TestGitRepository")
@withPrep(reposcenario.untrackedEmptyFile)
def testStageEmptyUntrackedFileFromDiffView(qtbot, workDir, rw):
    testutil.qlvClickNthRow(rw.dirtyView, 0)
    rw.diffView.setFocus()
    #self.breathe()
    QTest.keyPress(rw.diffView, Qt.Key_Return)
    #self.breathe()
    repo = pygit2.Repository(workDir)
    assert repo.status() == {}


@withRepo("TestEmptyRepository")
@withPrep(None)
def testEmptyRepo(qtbot, workDir, rw):
    assert rw


@withRepo("TestGitRepository")
@withPrep(reposcenario.fileWithUnstagedChange)
def testCommit(qtbot, workDir, rw):
    testutil.qlvClickNthRow(rw.dirtyView, 0)
    QTest.keyPress(rw.dirtyView, Qt.Key_Return)
    assert testutil.qlvGetTextRows(rw.dirtyView) == []
    assert testutil.qlvGetTextRows(rw.stageView) == ["a/a1.txt"]
    QTest.mouseClick(rw.commitButton, Qt.LeftButton)

    commitDialog: CommitDialog = rw.findChild(QDialog)
    assert "COMMIT" in commitDialog.windowTitle().upper()

    QTest.keyClicks(commitDialog.ui.summaryEditor, "Some New Commit")

    commitDialog.ui.revealAuthor.click()
    commitDialog.ui.authorSignature.ui.nameEdit.setText("Custom Author")
    commitDialog.ui.authorSignature.ui.emailEdit.setText("custom.author@example.com")
    enteredDate = QDateTime.fromString("1999-12-31 23:59:00", "yyyy-MM-dd HH:mm:ss")
    commitDialog.ui.authorSignature.ui.timeEdit.setDateTime(enteredDate)

    QTest.keyPress(commitDialog, Qt.Key_Return)

    repo = pygit2.Repository(workDir)
    headCommit: pygit2.Commit = repo.head.peel(pygit2.Commit)

    assert headCommit.message == "Some New Commit"
    assert headCommit.author.name == "Custom Author"
    assert headCommit.author.email == "custom.author@example.com"
    assert headCommit.author.time == QDateTime.toTime_t(enteredDate)

    assert len(headCommit.parents) == 1
    diff: pygit2.Diff = repo.diff(headCommit.parents[0], headCommit)
    patches: list[pygit2.Patch] = list(diff)
    assert len(patches) == 1
    assert patches[0].delta.new_file.path == "a/a1.txt"


@withRepo("TestGitRepository")
@withPrep(None)
def testSaveOldRevision(qtbot, workDir, tempDir, rw):
    commitOid = pygit2.Oid(binascii.unhexlify("6462e7d8024396b14d7651e2ec11e2bbf07a05c4"))

    rw.graphView.selectCommit(commitOid)
    assert testutil.qlvGetTextRows(rw.changedFilesView) == ["c/c2.txt"]
    rw.changedFilesView.selectRow(0)
    rw.changedFilesView.saveRevisionAs(saveInto=tempDir.name)

    with open(os.path.join(tempDir.name, "c2@6462e7d.txt"), "rb") as f:
        contents = f.read()
        assert contents == b"c2\n"
