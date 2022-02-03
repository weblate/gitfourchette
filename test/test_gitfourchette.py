from helpers.qttest_imports import *
from helpers import reposcenario, testutil
from helpers.fixtures import *
from widgets.commitdialog import CommitDialog
import pygit2


@withRepo("TestEmptyRepository")
@withPrep(None)
def testEmptyRepo(qtbot, workDir, rw):
    assert rw


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
    assert testutil.qlvGetRowData(rw.dirtyView) == ["SomeNewFile.txt"]
    assert testutil.qlvGetRowData(rw.stageView) == []


@withRepo("TestGitRepository")
@withPrep(reposcenario.nestedUntrackedFiles)
def testDisplayAllNestedUntrackedFiles(qtbot, workDir, rw):
    assert testutil.qlvGetRowData(rw.dirtyView) == ["N/tata.txt", "N/toto.txt", "N/tutu.txt"]
    assert testutil.qlvGetRowData(rw.stageView) == []


@withRepo("TestGitRepository")
@withPrep(reposcenario.untrackedEmptyFile)
def testStageEmptyUntrackedFile(qtbot, workDirRepo, rw):
    assert testutil.qlvGetRowData(rw.dirtyView) == ["SomeNewFile.txt"]
    assert testutil.qlvGetRowData(rw.stageView) == []

    testutil.qlvClickNthRow(rw.dirtyView, 0)
    QTest.keyPress(rw.dirtyView, Qt.Key_Return)

    assert testutil.qlvGetRowData(rw.dirtyView) == []
    assert testutil.qlvGetRowData(rw.stageView) == ["SomeNewFile.txt"]
    assert workDirRepo.status() == {"SomeNewFile.txt": pygit2.GIT_STATUS_INDEX_NEW}


@withRepo("TestGitRepository")
@withPrep(reposcenario.untrackedEmptyFile)
def testDiscardUntrackedFile(qtbot, workDirRepo, rw):
    assert testutil.qlvGetRowData(rw.dirtyView) == ["SomeNewFile.txt"]
    testutil.qlvClickNthRow(rw.dirtyView, 0)

    QTest.keyPress(rw.dirtyView, Qt.Key_Delete)

    testutil.acceptQMessageBox(rw, "discard changes")

    assert rw.dirtyView.model().rowCount() == 0
    assert rw.stageView.model().rowCount() == 0
    assert workDirRepo.status() == {}


@withRepo("TestGitRepository")
@withPrep(reposcenario.fileWithUnstagedChange)
def testDiscardUnstagedFileModification(qtbot, workDirRepo, rw):
    assert testutil.qlvGetRowData(rw.dirtyView) == ["a/a1.txt"]
    assert testutil.qlvGetRowData(rw.stageView) == []
    testutil.qlvClickNthRow(rw.dirtyView, 0)

    QTest.keyPress(rw.dirtyView, Qt.Key_Delete)

    testutil.acceptQMessageBox(rw, "discard changes")

    assert testutil.qlvGetRowData(rw.dirtyView) == []
    assert testutil.qlvGetRowData(rw.stageView) == []
    assert workDirRepo.status() == {}


@withRepo("TestGitRepository")
@withPrep(reposcenario.fileWithStagedAndUnstagedChanges)
def testDiscardFileModificationWithoutAffectingStagedChange(qtbot, workDirRepo, rw):
    assert testutil.qlvGetRowData(rw.dirtyView) == ["a/a1.txt"]
    assert testutil.qlvGetRowData(rw.stageView) == ["a/a1.txt"]
    testutil.qlvClickNthRow(rw.dirtyView, 0)
    QTest.keyPress(rw.dirtyView, Qt.Key_Delete)

    testutil.acceptQMessageBox(rw, "discard changes")

    assert testutil.qlvGetRowData(rw.dirtyView) == []
    assert testutil.qlvGetRowData(rw.stageView) == ["a/a1.txt"]
    assert workDirRepo.status() == {"a/a1.txt": pygit2.GIT_STATUS_INDEX_MODIFIED}


@withRepo("TestEmptyRepository")
@withPrep(reposcenario.stagedNewEmptyFile)
def testUnstageChangeInEmptyRepo(qtbot, workDirRepo, rw):
    assert testutil.qlvGetRowData(rw.dirtyView) == []
    assert testutil.qlvGetRowData(rw.stageView) == ["SomeNewFile.txt"]
    testutil.qlvClickNthRow(rw.stageView, 0)
    QTest.keyPress(rw.stageView, Qt.Key_Delete)

    assert testutil.qlvGetRowData(rw.dirtyView) == ["SomeNewFile.txt"]
    assert testutil.qlvGetRowData(rw.stageView) == []

    assert workDirRepo.status() == {"SomeNewFile.txt": pygit2.GIT_STATUS_WT_NEW}


@withRepo("TestGitRepository")
@withPrep(reposcenario.untrackedEmptyFile)
def testStageEmptyUntrackedFileFromDiffView(qtbot, workDir, rw):
    testutil.qlvClickNthRow(rw.dirtyView, 0)
    rw.diffView.setFocus()
    QTest.keyPress(rw.diffView, Qt.Key_Return)
    repo = pygit2.Repository(workDir)
    assert repo.status() == {}


@withRepo("TestGitRepository")
@withPrep(None)
def testParentlessCommitFileList(qtbot, workDir, rw):
    commitOid = testutil.hexToOid("42e4e7c5e507e113ebbb7801b16b52cf867b7ce1")

    rw.graphView.selectCommit(commitOid)

    assert testutil.qlvGetRowData(rw.changedFilesView) == ["c/c1.txt"]


@withRepo("TestGitRepository")
@withPrep(reposcenario.fileWithUnstagedChange)
def testCommit(qtbot, workDirRepo, rw):
    testutil.qlvClickNthRow(rw.dirtyView, 0)
    QTest.keyPress(rw.dirtyView, Qt.Key_Return)
    assert testutil.qlvGetRowData(rw.dirtyView) == []
    assert testutil.qlvGetRowData(rw.stageView) == ["a/a1.txt"]
    rw.commitButton.click()

    dialog: CommitDialog = testutil.findQDialog(rw, "commit")
    QTest.keyClicks(dialog.ui.summaryEditor, "Some New Commit")

    dialog.ui.revealAuthor.click()
    dialog.ui.authorSignature.ui.nameEdit.setText("Custom Author")
    dialog.ui.authorSignature.ui.emailEdit.setText("custom.author@example.com")
    enteredDate = QDateTime.fromString("1999-12-31 23:59:00", "yyyy-MM-dd HH:mm:ss")
    dialog.ui.authorSignature.ui.timeEdit.setDateTime(enteredDate)

    dialog.accept()

    headCommit: pygit2.Commit = workDirRepo.head.peel(pygit2.Commit)

    assert headCommit.message == "Some New Commit"
    assert headCommit.author.name == "Custom Author"
    assert headCommit.author.email == "custom.author@example.com"
    assert headCommit.author.time == QDateTime.toTime_t(enteredDate)

    assert len(headCommit.parents) == 1
    diff: pygit2.Diff = workDirRepo.diff(headCommit.parents[0], headCommit)
    patches: list[pygit2.Patch] = list(diff)
    assert len(patches) == 1
    assert patches[0].delta.new_file.path == "a/a1.txt"


@withRepo("TestEmptyRepository")
@withPrep(reposcenario.untrackedEmptyFile)
def testCommitUntrackedFileInEmptyRepo(qtbot, rw):
    testutil.qlvClickNthRow(rw.dirtyView, 0)
    QTest.keyPress(rw.dirtyView, Qt.Key_Return)

    assert testutil.qlvGetRowData(rw.dirtyView) == []
    assert testutil.qlvGetRowData(rw.stageView) == ["SomeNewFile.txt"]

    rw.commitButton.click()
    dialog: CommitDialog = testutil.findQDialog(rw, "commit")
    QTest.keyClicks(dialog.ui.summaryEditor, "Initial commit")
    dialog.accept()

    rows = testutil.qlvGetRowData(rw.graphView)
    commit: pygit2.Commit = rows[-1].peel(pygit2.Commit)
    assert commit.message == "Initial commit"


@withRepo("TestGitRepository")
@withPrep(reposcenario.stagedNewEmptyFile)
def testCommitMessageDraftSavedOnCancel(qtbot, rw):
    testutil.qlvClickNthRow(rw.dirtyView, 0)
    QTest.keyPress(rw.dirtyView, Qt.Key_Return)

    rw.commitButton.click()
    dialog: CommitDialog = testutil.findQDialog(rw, "commit")
    assert dialog.ui.summaryEditor.text() == ""
    QTest.keyClicks(dialog.ui.summaryEditor, "hoping to save this message")
    dialog.reject()

    rw.commitButton.click()
    dialog: CommitDialog = testutil.findQDialog(rw, "commit")
    assert dialog.ui.summaryEditor.text() == "hoping to save this message"
    dialog.reject()


@withRepo("TestGitRepository")
@withPrep(reposcenario.stagedNewEmptyFile)
def testAmendCommit(qtbot, workDirRepo, rw):
    testutil.qlvClickNthRow(rw.dirtyView, 0)
    QTest.keyPress(rw.dirtyView, Qt.Key_Return)

    rw.amendButton.click()
    dialog: CommitDialog = testutil.findQDialog(rw, "amend")
    assert dialog.ui.summaryEditor.text() == "Delete c/c2-2.txt"
    dialog.ui.summaryEditor.setText("amended commit message")
    dialog.accept()

    headCommit: pygit2.Commit = workDirRepo.head.peel(pygit2.Commit)
    assert headCommit.message == "amended commit message"


@withRepo("TestGitRepository")
@withPrep(None)
def testEmptyCommitRaisesWarning(qtbot, workDirRepo, rw):
    rw.commitButton.click()
    q = testutil.findQDialog(rw, "empty commit")
    q.reject()


@withRepo("TestGitRepository")
@withPrep(None)
def testSaveOldRevision(qtbot, workDir, tempDir, rw):
    commitOid = testutil.hexToOid("6462e7d8024396b14d7651e2ec11e2bbf07a05c4")

    rw.graphView.selectCommit(commitOid)
    assert testutil.qlvGetRowData(rw.changedFilesView) == ["c/c2.txt"]
    rw.changedFilesView.selectRow(0)
    rw.changedFilesView.saveRevisionAs(saveInto=tempDir.name)

    with open(F"{tempDir.name}/c2@6462e7d.txt", "rb") as f:
        contents = f.read()
        assert contents == b"c2\n"


@withRepo("TestGitRepository")
@withPrep(None)
def testSaveOldRevisionOfDeletedFile(qtbot, workDir, tempDir, rw):
    commitOid = testutil.hexToOid("c9ed7bf12c73de26422b7c5a44d74cfce5a8993b")

    rw.graphView.selectCommit(commitOid)
    assert testutil.qlvGetRowData(rw.changedFilesView) == ["c/c2-2.txt"]
    rw.changedFilesView.selectRow(0)
    rw.changedFilesView.saveRevisionAs(saveInto=tempDir.name)

    # c2-2.txt was deleted by the commit.
    # Expect GF to save the state of the file before its deletion.
    with open(F"{tempDir.name}/c2-2@c9ed7bf.txt", "rb") as f:
        contents = f.read()
        assert contents == b"c2\nc2\n"

