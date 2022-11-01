from . import reposcenario
from .fixtures import *
from .util import *
from gitfourchette.widgets.commitdialog import CommitDialog
import pygit2


def testEmptyRepo(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir, "TestEmptyRepository")
    assert mainWindow.openRepo(wd)
    assert mainWindow.tabs.count() == 1
    mainWindow.closeCurrentTab()  # mustn't crash
    assert mainWindow.tabs.count() == 0


def testChangedFilesShownAtStart(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    touchFile(F"{wd}/SomeNewFile.txt")
    rw = mainWindow.openRepo(wd)

    assert rw.graphView.model().rowCount() > 5
    assert rw.dirtyFiles.isVisibleTo(rw)
    assert rw.stagedFiles.isVisibleTo(rw)
    assert not rw.committedFiles.isVisibleTo(rw)
    assert qlvGetRowData(rw.dirtyFiles) == ["SomeNewFile.txt"]
    assert qlvGetRowData(rw.stagedFiles) == []


def testDisplayAllNestedUntrackedFiles(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    os.mkdir(F"{wd}/N")
    touchFile(F"{wd}/N/tata.txt")
    touchFile(F"{wd}/N/toto.txt")
    touchFile(F"{wd}/N/tutu.txt")
    rw = mainWindow.openRepo(wd)
    assert qlvGetRowData(rw.dirtyFiles) == ["N/tata.txt", "N/toto.txt", "N/tutu.txt"]
    assert qlvGetRowData(rw.stagedFiles) == []


def testStageEmptyUntrackedFile(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    touchFile(F"{wd}/SomeNewFile.txt")
    rw = mainWindow.openRepo(wd)

    assert qlvGetRowData(rw.dirtyFiles) == ["SomeNewFile.txt"]
    assert qlvGetRowData(rw.stagedFiles) == []

    qlvClickNthRow(rw.dirtyFiles, 0)
    QTest.keyPress(rw.dirtyFiles, Qt.Key_Return)

    assert qlvGetRowData(rw.dirtyFiles) == []
    assert qlvGetRowData(rw.stagedFiles) == ["SomeNewFile.txt"]
    assert rw.repo.status() == {"SomeNewFile.txt": pygit2.GIT_STATUS_INDEX_NEW}


def testDiscardUntrackedFile(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    touchFile(F"{wd}/SomeNewFile.txt")
    rw = mainWindow.openRepo(wd)

    assert qlvGetRowData(rw.dirtyFiles) == ["SomeNewFile.txt"]
    qlvClickNthRow(rw.dirtyFiles, 0)

    QTest.keyPress(rw.dirtyFiles, Qt.Key_Delete)

    acceptQMessageBox(rw, "discard changes")

    assert rw.dirtyFiles.model().rowCount() == 0
    assert rw.stagedFiles.model().rowCount() == 0
    assert rw.repo.status() == {}


def testDiscardUnstagedFileModification(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    writeFile(F"{wd}/a/a1.txt", "a1\nPENDING CHANGE\n")  # unstaged change
    rw = mainWindow.openRepo(wd)

    assert qlvGetRowData(rw.dirtyFiles) == ["a/a1.txt"]
    assert qlvGetRowData(rw.stagedFiles) == []
    qlvClickNthRow(rw.dirtyFiles, 0)

    QTest.keyPress(rw.dirtyFiles, Qt.Key_Delete)

    acceptQMessageBox(rw, "discard changes")

    assert qlvGetRowData(rw.dirtyFiles) == []
    assert qlvGetRowData(rw.stagedFiles) == []
    assert rw.repo.status() == {}


def testDiscardFileModificationWithoutAffectingStagedChange(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    reposcenario.fileWithStagedAndUnstagedChanges(wd)
    rw = mainWindow.openRepo(wd)

    assert qlvGetRowData(rw.dirtyFiles) == ["a/a1.txt"]
    assert qlvGetRowData(rw.stagedFiles) == ["a/a1.txt"]
    qlvClickNthRow(rw.dirtyFiles, 0)
    QTest.keyPress(rw.dirtyFiles, Qt.Key_Delete)

    acceptQMessageBox(rw, "discard changes")

    assert qlvGetRowData(rw.dirtyFiles) == []
    assert qlvGetRowData(rw.stagedFiles) == ["a/a1.txt"]
    assert rw.repo.status() == {"a/a1.txt": pygit2.GIT_STATUS_INDEX_MODIFIED}


def testUnstageChangeInEmptyRepo(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir, "TestEmptyRepository")
    reposcenario.stagedNewEmptyFile(wd)
    rw = mainWindow.openRepo(wd)

    assert qlvGetRowData(rw.dirtyFiles) == []
    assert qlvGetRowData(rw.stagedFiles) == ["SomeNewFile.txt"]
    qlvClickNthRow(rw.stagedFiles, 0)
    QTest.keyPress(rw.stagedFiles, Qt.Key_Delete)

    assert qlvGetRowData(rw.dirtyFiles) == ["SomeNewFile.txt"]
    assert qlvGetRowData(rw.stagedFiles) == []

    assert rw.repo.status() == {"SomeNewFile.txt": pygit2.GIT_STATUS_WT_NEW}


def testParentlessCommitFileList(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)

    commitOid = hexToOid("42e4e7c5e507e113ebbb7801b16b52cf867b7ce1")
    rw.graphView.selectCommit(commitOid)
    assert qlvGetRowData(rw.committedFiles) == ["c/c1.txt"]


def testCommit(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    writeFile(F"{wd}/a/a1.txt", "a1\nPENDING CHANGE\n")  # unstaged change
    rw = mainWindow.openRepo(wd)

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

    headCommit: pygit2.Commit = rw.repo.head.peel(pygit2.Commit)

    assert headCommit.message == "Some New Commit"
    assert headCommit.author.name == "Custom Author"
    assert headCommit.author.email == "custom.author@example.com"
    assert headCommit.author.time == enteredDate.toSecsSinceEpoch()

    assert len(headCommit.parents) == 1
    diff: pygit2.Diff = rw.repo.diff(headCommit.parents[0], headCommit)
    patches: list[pygit2.Patch] = list(diff)
    assert len(patches) == 1
    assert patches[0].delta.new_file.path == "a/a1.txt"


def testCommitUntrackedFileInEmptyRepo(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir, "TestEmptyRepository")
    touchFile(F"{wd}/SomeNewFile.txt")
    rw = mainWindow.openRepo(wd)

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


def testCommitMessageDraftSavedOnCancel(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    reposcenario.stagedNewEmptyFile(wd)
    rw = mainWindow.openRepo(wd)

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


def testAmendCommit(qtbot, tempDir, mainWindow):
    oldMessage = "Delete c/c2-2.txt"
    newMessage = "amended commit message"
    newAuthorName = "Jean-Michel Tartempion"
    newAuthorEmail = "jmtartempion@example.com"

    wd = unpackRepo(tempDir)
    reposcenario.stagedNewEmptyFile(wd)
    rw = mainWindow.openRepo(wd)

    # Select file
    qlvClickNthRow(rw.dirtyFiles, 0)

    # Stage it
    QTest.keyPress(rw.dirtyFiles, Qt.Key_Return)

    # Kick off amend dialog
    rw.amendButton.click()

    dialog: CommitDialog = findQDialog(rw, "amend")
    assert dialog.ui.summaryEditor.text() == oldMessage
    dialog.ui.summaryEditor.setText(newMessage)
    dialog.ui.revealAuthor.setChecked(True)
    dialog.ui.authorSignature.ui.nameEdit.setText(newAuthorName)
    dialog.ui.authorSignature.ui.emailEdit.setText(newAuthorEmail)
    dialog.accept()

    headCommit: pygit2.Commit = rw.repo.head.peel(pygit2.Commit)
    assert headCommit.message == newMessage
    assert headCommit.author.name == newAuthorName
    assert headCommit.author.email == newAuthorEmail


def testEmptyCommitRaisesWarning(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    rw.commitButton.click()
    q = findQDialog(rw, "empty commit")
    q.reject()


def testSaveOldRevision(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)

    commitOid = hexToOid("6462e7d8024396b14d7651e2ec11e2bbf07a05c4")

    rw.graphView.selectCommit(commitOid)
    assert qlvGetRowData(rw.committedFiles) == ["c/c2.txt"]
    rw.committedFiles.selectRow(0)
    rw.committedFiles.saveRevisionAs(saveInto=tempDir.name)

    with open(F"{tempDir.name}/c2@6462e7d.txt", "rb") as f:
        contents = f.read()
        assert contents == b"c2\n"


def testSaveOldRevisionOfDeletedFile(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)

    commitOid = hexToOid("c9ed7bf12c73de26422b7c5a44d74cfce5a8993b")

    rw.graphView.selectCommit(commitOid)
    assert qlvGetRowData(rw.committedFiles) == ["c/c2-2.txt"]
    rw.committedFiles.selectRow(0)

    # c2-2.txt was deleted by the commit.
    # Expect GF to warn us about it.
    rw.committedFiles.saveRevisionAs(saveInto=tempDir.name, beforeCommit=False)
    acceptQMessageBox(rw, r"save.+revision", r"file.+deleted by.+commit")


def testCheckoutCommit(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    repo = rw.repo

    oid = pygit2.Oid(hex="0966a434eb1a025db6b71485ab63a3bfbea520b6")
    rw.graphView.selectCommit(oid)
    rw.graphView.checkoutCommit.emit(oid)

    assert repo.head_is_detached
    assert repo.head.peel(pygit2.Commit).oid == oid
