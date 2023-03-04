from . import reposcenario
from .fixtures import *
from .util import *
from gitfourchette import porcelain
from gitfourchette.commitlogmodel import CommitLogModel
from gitfourchette.widgets.commitdialog import CommitDialog
from gitfourchette.widgets.resetheaddialog import ResetHeadDialog
import pygit2


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

    rows = qlvGetRowData(rw.graphView, CommitLogModel.CommitRole)
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
    with qtbot.waitSignal(dialog.destroyed):  # upon exiting context, wait for dialog to be gone
        dialog.accept()

    headCommit: pygit2.Commit = rw.repo.head.peel(pygit2.Commit)
    assert headCommit.message == newMessage
    assert headCommit.author.name == newAuthorName
    assert headCommit.author.email == newAuthorEmail

    # Ensure no error dialog boxes after operation
    assert not mainWindow.findChildren(QDialog)

    assert not rw.graphView.currentCommitOid  # "uncommitted changes" should still be selected
    assert rw.stagedFiles.isVisibleTo(rw)
    assert rw.dirtyFiles.isVisibleTo(rw)
    assert not rw.committedFiles.isVisibleTo(rw)


def testAmendCommitDontBreakRefresh(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    reposcenario.stagedNewEmptyFile(wd)
    rw = mainWindow.openRepo(wd)

    headOid = porcelain.getHeadCommitOid(rw.repo)
    rw.graphView.selectCommit(headOid)

    # Kick off amend dialog
    mainWindow.amend()

    # Amend HEAD commit without any changes, i.e. just change the timestamp.
    dialog: CommitDialog = findQDialog(rw, "amend")
    with qtbot.waitSignal(dialog.destroyed):  # upon exiting context, wait for dialog to be gone
        dialog.accept()

    # Ensure no errors dialog boxes after operation (e.g. "commit not found")
    assert not mainWindow.findChildren(QDialog)


def testEmptyCommitRaisesWarning(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    rw.commitButton.click()
    rejectQMessageBox(rw, "create.+empty commit")


def testResetHeadToCommit(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)

    oid1 = pygit2.Oid(hex="0966a434eb1a025db6b71485ab63a3bfbea520b6")

    assert rw.repo.head.target != oid1  # make sure we're not starting from this commit
    assert rw.repo.branches.local['master'].target != oid1

    rw.graphView.selectCommit(oid1)
    rw.graphView.resetHeadFlow()

    qd: ResetHeadDialog = findQDialog(rw, "reset head to 0966a4")
    qd.modeButtons['hard'].click()
    qd.accept()

    assert rw.repo.head.target == oid1
    assert rw.repo.branches.local['master'].target == oid1


def testCheckoutCommitDetachedHead(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    repo = rw.repo

    for oid in [pygit2.Oid(hex="0966a434eb1a025db6b71485ab63a3bfbea520b6"),
                pygit2.Oid(hex="6db9c2ebf75590eef973081736730a9ea169a0c4"),
                ]:
        rw.graphView.selectCommit(oid)
        rw.graphView.checkoutCommit.emit(oid)

        dlg = findQDialog(rw, "check.?out commit")
        dlg.findChild(QRadioButton, "detachedHeadRadioButton", Qt.FindChildOption.FindChildrenRecursively).setChecked(True)
        dlg.accept()

        assert repo.head_is_detached
        assert repo.head.peel(pygit2.Commit).oid == oid

        assert rw.graphView.currentCommitOid == oid, "graphview's selected commit has jumped around"


def testCommitOnDetachedHead(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)

    oid = pygit2.Oid(hex='1203b03dc816ccbb67773f28b3c19318654b0bc8')

    repo = pygit2.Repository(wd)
    porcelain.checkoutCommit(repo, oid)
    repo.free()  # necessary for correct test teardown on Windows
    del repo

    rw = mainWindow.openRepo(wd)

    assert rw.repo.head_is_detached
    assert rw.repo.head.target == oid

    displayedCommits = qlvGetRowData(rw.graphView, Qt.ItemDataRole.UserRole)
    assert rw.repo.head.peel(pygit2.Commit) in displayedCommits

    rw.commitButton.click()
    acceptQMessageBox(rw, "create.+empty commit")
    commitDialog: CommitDialog = findQDialog(rw, "commit")
    commitDialog.ui.summaryEditor.setText("les chenilles et les chevaux")
    commitDialog.accept()

    assert rw.repo.head_is_detached
    assert rw.repo.head.target != oid  # detached HEAD should no longer point to initial commit

    newHeadCommit: pygit2.Commit = rw.repo.head.peel(pygit2.Commit)
    assert newHeadCommit.message == "les chenilles et les chevaux"

    displayedCommits = qlvGetRowData(rw.graphView, Qt.ItemDataRole.UserRole)
    assert newHeadCommit in displayedCommits


def testRevertCommit(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)

    oid = pygit2.Oid(hex="c9ed7bf12c73de26422b7c5a44d74cfce5a8993b")
    rw.graphView.selectCommit(oid)
    rw.graphView.revertCommit.emit(oid)

    rw.graphView.uncommittedChangesClicked.emit()
    assert qlvGetRowData(rw.stagedFiles) == ["c/c2-2.txt"]
    assert rw.repo.status() == {"c/c2-2.txt": pygit2.GIT_STATUS_INDEX_NEW}
