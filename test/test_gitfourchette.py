from . import reposcenario
from .fixtures import *
from .util import *
from gitfourchette.widgets.commitdialog import CommitDialog
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
    assert rw.dirtyFiles.isVisibleTo(rw)
    assert rw.stagedFiles.isVisibleTo(rw)
    assert not rw.committedFiles.isVisibleTo(rw)
    assert qlvGetRowData(rw.dirtyFiles) == ["SomeNewFile.txt"]
    assert qlvGetRowData(rw.stagedFiles) == []


@withRepo("TestGitRepository")
@withPrep(reposcenario.nestedUntrackedFiles)
def testDisplayAllNestedUntrackedFiles(qtbot, workDir, rw):
    assert qlvGetRowData(rw.dirtyFiles) == ["N/tata.txt", "N/toto.txt", "N/tutu.txt"]
    assert qlvGetRowData(rw.stagedFiles) == []


@withRepo("TestGitRepository")
@withPrep(reposcenario.untrackedEmptyFile)
def testStageEmptyUntrackedFile(qtbot, workDirRepo, rw):
    assert qlvGetRowData(rw.dirtyFiles) == ["SomeNewFile.txt"]
    assert qlvGetRowData(rw.stagedFiles) == []

    qlvClickNthRow(rw.dirtyFiles, 0)
    QTest.keyPress(rw.dirtyFiles, Qt.Key_Return)

    assert qlvGetRowData(rw.dirtyFiles) == []
    assert qlvGetRowData(rw.stagedFiles) == ["SomeNewFile.txt"]
    assert workDirRepo.status() == {"SomeNewFile.txt": pygit2.GIT_STATUS_INDEX_NEW}


@withRepo("TestGitRepository")
@withPrep(reposcenario.untrackedEmptyFile)
def testDiscardUntrackedFile(qtbot, workDirRepo, rw):
    assert qlvGetRowData(rw.dirtyFiles) == ["SomeNewFile.txt"]
    qlvClickNthRow(rw.dirtyFiles, 0)

    QTest.keyPress(rw.dirtyFiles, Qt.Key_Delete)

    acceptQMessageBox(rw, "discard changes")

    assert rw.dirtyFiles.model().rowCount() == 0
    assert rw.stagedFiles.model().rowCount() == 0
    assert workDirRepo.status() == {}


@withRepo("TestGitRepository")
@withPrep(reposcenario.fileWithUnstagedChange)
def testDiscardUnstagedFileModification(qtbot, workDirRepo, rw):
    assert qlvGetRowData(rw.dirtyFiles) == ["a/a1.txt"]
    assert qlvGetRowData(rw.stagedFiles) == []
    qlvClickNthRow(rw.dirtyFiles, 0)

    QTest.keyPress(rw.dirtyFiles, Qt.Key_Delete)

    acceptQMessageBox(rw, "discard changes")

    assert qlvGetRowData(rw.dirtyFiles) == []
    assert qlvGetRowData(rw.stagedFiles) == []
    assert workDirRepo.status() == {}


@withRepo("TestGitRepository")
@withPrep(reposcenario.fileWithStagedAndUnstagedChanges)
def testDiscardFileModificationWithoutAffectingStagedChange(qtbot, workDirRepo, rw):
    assert qlvGetRowData(rw.dirtyFiles) == ["a/a1.txt"]
    assert qlvGetRowData(rw.stagedFiles) == ["a/a1.txt"]
    qlvClickNthRow(rw.dirtyFiles, 0)
    QTest.keyPress(rw.dirtyFiles, Qt.Key_Delete)

    acceptQMessageBox(rw, "discard changes")

    assert qlvGetRowData(rw.dirtyFiles) == []
    assert qlvGetRowData(rw.stagedFiles) == ["a/a1.txt"]
    assert workDirRepo.status() == {"a/a1.txt": pygit2.GIT_STATUS_INDEX_MODIFIED}


@withRepo("TestEmptyRepository")
@withPrep(reposcenario.stagedNewEmptyFile)
def testUnstageChangeInEmptyRepo(qtbot, workDirRepo, rw):
    assert qlvGetRowData(rw.dirtyFiles) == []
    assert qlvGetRowData(rw.stagedFiles) == ["SomeNewFile.txt"]
    qlvClickNthRow(rw.stagedFiles, 0)
    QTest.keyPress(rw.stagedFiles, Qt.Key_Delete)

    assert qlvGetRowData(rw.dirtyFiles) == ["SomeNewFile.txt"]
    assert qlvGetRowData(rw.stagedFiles) == []

    assert workDirRepo.status() == {"SomeNewFile.txt": pygit2.GIT_STATUS_WT_NEW}


@withRepo("TestGitRepository")
@withPrep(None)
def testStageUntrackedFileFromDiffView(qtbot, workDirRepo, rw):
    writeFile(F"{workDirRepo.workdir}/NewFile.txt", "line A\nline B\nline C\n")
    rw.quickRefresh()

    qlvClickNthRow(rw.dirtyFiles, 0)
    assert workDirRepo.status() == {"NewFile.txt": pygit2.GIT_STATUS_WT_NEW}

    rw.diffView.setFocus()
    QTest.keyPress(rw.diffView, Qt.Key_Return)

    assert workDirRepo.status() == {"NewFile.txt": pygit2.GIT_STATUS_INDEX_NEW | pygit2.GIT_STATUS_WT_MODIFIED}

    stagedId = workDirRepo.index["NewFile.txt"].id
    stagedBlob: pygit2.Blob = workDirRepo[stagedId].peel(pygit2.Blob)
    assert stagedBlob.data == b"line A\n"


@withRepo("TestGitRepository")
@withPrep(None)
def testParentlessCommitFileList(qtbot, workDir, rw):
    commitOid = hexToOid("42e4e7c5e507e113ebbb7801b16b52cf867b7ce1")

    rw.graphView.selectCommit(commitOid)

    assert qlvGetRowData(rw.committedFiles) == ["c/c1.txt"]


@withRepo("TestGitRepository")
@withPrep(reposcenario.fileWithUnstagedChange)
def testCommit(qtbot, workDirRepo, rw):
    qlvClickNthRow(rw.dirtyFiles, 0)
    QTest.keyPress(rw.dirtyFiles, Qt.Key_Return)
    assert qlvGetRowData(rw.dirtyFiles) == []
    assert qlvGetRowData(rw.stagedFiles) == ["a/a1.txt"]
    rw.commitButton.click()

    dialog: CommitDialog = findQDialog(rw, "commit")
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
    qlvClickNthRow(rw.dirtyFiles, 0)
    QTest.keyPress(rw.dirtyFiles, Qt.Key_Return)

    assert qlvGetRowData(rw.dirtyFiles) == []
    assert qlvGetRowData(rw.stagedFiles) == ["SomeNewFile.txt"]

    rw.commitButton.click()
    dialog: CommitDialog = findQDialog(rw, "commit")
    QTest.keyClicks(dialog.ui.summaryEditor, "Initial commit")
    dialog.accept()

    rows = qlvGetRowData(rw.graphView)
    commit: pygit2.Commit = rows[-1].peel(pygit2.Commit)
    assert commit.message == "Initial commit"


@withRepo("TestGitRepository")
@withPrep(reposcenario.stagedNewEmptyFile)
def testCommitMessageDraftSavedOnCancel(qtbot, rw):
    qlvClickNthRow(rw.dirtyFiles, 0)
    QTest.keyPress(rw.dirtyFiles, Qt.Key_Return)

    rw.commitButton.click()
    dialog: CommitDialog = findQDialog(rw, "commit")
    assert dialog.ui.summaryEditor.text() == ""
    QTest.keyClicks(dialog.ui.summaryEditor, "hoping to save this message")
    dialog.reject()

    rw.commitButton.click()
    dialog: CommitDialog = findQDialog(rw, "commit")
    assert dialog.ui.summaryEditor.text() == "hoping to save this message"
    dialog.reject()


@withRepo("TestGitRepository")
@withPrep(reposcenario.stagedNewEmptyFile)
def testAmendCommit(qtbot, workDirRepo, rw):
    qlvClickNthRow(rw.dirtyFiles, 0)
    QTest.keyPress(rw.dirtyFiles, Qt.Key_Return)

    rw.amendButton.click()
    dialog: CommitDialog = findQDialog(rw, "amend")
    assert dialog.ui.summaryEditor.text() == "Delete c/c2-2.txt"
    dialog.ui.summaryEditor.setText("amended commit message")
    dialog.accept()

    headCommit: pygit2.Commit = workDirRepo.head.peel(pygit2.Commit)
    assert headCommit.message == "amended commit message"


@withRepo("TestGitRepository")
@withPrep(None)
def testEmptyCommitRaisesWarning(qtbot, workDirRepo, rw):
    rw.commitButton.click()
    q = findQDialog(rw, "empty commit")
    q.reject()


@withRepo("TestGitRepository")
@withPrep(None)
def testSaveOldRevision(qtbot, workDir, tempDir, rw):
    commitOid = hexToOid("6462e7d8024396b14d7651e2ec11e2bbf07a05c4")

    rw.graphView.selectCommit(commitOid)
    assert qlvGetRowData(rw.committedFiles) == ["c/c2.txt"]
    rw.committedFiles.selectRow(0)
    rw.committedFiles.saveRevisionAs(saveInto=tempDir.name)

    with open(F"{tempDir.name}/c2@6462e7d.txt", "rb") as f:
        contents = f.read()
        assert contents == b"c2\n"


@withRepo("TestGitRepository")
@withPrep(None)
def testSaveOldRevisionOfDeletedFile(qtbot, workDir, tempDir, rw):
    commitOid = hexToOid("c9ed7bf12c73de26422b7c5a44d74cfce5a8993b")

    rw.graphView.selectCommit(commitOid)
    assert qlvGetRowData(rw.committedFiles) == ["c/c2-2.txt"]
    rw.committedFiles.selectRow(0)
    rw.committedFiles.saveRevisionAs(saveInto=tempDir.name)

    # c2-2.txt was deleted by the commit.
    # Expect GF to save the state of the file before its deletion.
    with open(F"{tempDir.name}/c2-2@c9ed7bf.txt", "rb") as f:
        contents = f.read()
        assert contents == b"c2\nc2\n"

