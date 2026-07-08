# -----------------------------------------------------------------------------
# Copyright (C) 2026 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

import dataclasses

from gitfourchette.forms.commitdialog import CommitDialog
from gitfourchette.forms.rebasedialog import RebaseDialog
from gitfourchette.nav import NavLocator
from gitfourchette.rebase.rebasemodel import RebaseOp, RebaseOpLetters
from .util import *


@dataclasses.dataclass
class _Todo:
    row: int
    op: RebaseOp
    message: str = ""


def _driveRebaseDialog(rw, onto: Oid, todoList: list[_Todo]):
    rw.jump(NavLocator.inCommit(onto, ""))

    with AsynchronousTaskContext(rw.taskRunner):
        # Bring up RebaseDialog
        triggerContextMenuAction(rw.graphView.viewport(), "rebase")
        rebaseDialog = waitForQDialog(rw, "rebase", t=RebaseDialog)

        sequenceView = rebaseDialog.ui.sequence

        # Apply all operations
        for todo in todoList:
            # Select row
            qlvClickNthRow(sequenceView, todo.row)

            # Press keyboard shortcut for desired operation
            QTest.keyClicks(sequenceView.viewport(), RebaseOpLetters[todo.op])
            QTest.qWait(0)

            itemsSoFar = sequenceView.allRebaseLines()
            assert itemsSoFar[todo.row].op == todo.op

            # Apply reworded message, if any
            if todo.message:
                assert todo.op.isEditable(), "need editable op to change message"

                # Bring up QLineEdit
                if MACOS:
                    qlvClickNthRow(sequenceView, todo.row, doubleClick=True)
                else:
                    QTest.keyPress(sequenceView.viewport(), Qt.Key.Key_F2)

                lineEdit: QLineEdit = sequenceView.findChild(QLineEdit)
                assert lineEdit is not None
                assert lineEdit.hasFocus()

                # Fill it in
                QTest.keyClicks(lineEdit, todo.message)

                # Warning: in real life, Return commits the current text in the
                # QLineEdit, but in offscreen mode, this accepts the entire
                # dialog. Just use tab to commit instead...
                QTest.keyPress(lineEdit, Qt.Key.Key_Tab)
                QTest.qWait(0)

        # Go ahead with the rebase
        rebaseDialog.accept()


def testCancelRebaseDialog(tempDir, mainWindow):
    wd = unpackRepo(tempDir)

    rw = mainWindow.openRepo(wd)
    rw.jump(NavLocator.inCommit(Oid(hex="49322bb17d3acc9146f98c97d078513228bbf3c0"), "a/a1"), check=True)

    with AsynchronousTaskContext(rw.taskRunner):
        triggerContextMenuAction(rw.graphView.viewport(), "rebase")
        rebaseDialog = waitForQDialog(rw, "rebase", t=RebaseDialog)
        rebaseDialog.reject()

    rejectQMessageBox(rw, "exited with code")


def testAbortRebase(tempDir, mainWindow):
    head = Oid(hex="c9ed7bf12c73de26422b7c5a44d74cfce5a8993b")
    onto = Oid(hex="49322bb17d3acc9146f98c97d078513228bbf3c0")
    edit = Oid(hex="ce112d052bcf42442aa8563f1e2b7a8aabbf4d17")
    todo = [_Todo(0, RebaseOp.Edit)]

    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    _driveRebaseDialog(rw, onto, todo)

    assert rw.repo.state() == RepositoryState.REBASE_INTERACTIVE
    assert rw.repo.head_commit_id == edit
    assert rw.mergeBanner.isVisible()
    assert findTextInWidget(rw.mergeBanner.label, "rebasing.+master.+onto.+" + str(onto)[:7])
    assert findTextInWidget(rw.mergeBanner.label, "stopped at.+" + str(edit)[:7])

    # Abort the rebase
    abortButton = next(button for button in rw.mergeBanner.buttons
                       if findTextInWidget(button, "abort rebase"))
    abortButton.click()
    acceptQMessageBox(rw, "abort rebase")

    assert rw.repo.state() == RepositoryState.NONE
    assert not rw.mergeBanner.isVisible()
    assert rw.repo.head_commit_id == head


def testContinueRebase(tempDir, mainWindow):
    head = Oid(hex="c9ed7bf12c73de26422b7c5a44d74cfce5a8993b")
    onto = Oid(hex="49322bb17d3acc9146f98c97d078513228bbf3c0")
    edit = Oid(hex="ce112d052bcf42442aa8563f1e2b7a8aabbf4d17")
    todo = [_Todo(0, RebaseOp.Edit)]

    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    _driveRebaseDialog(rw, onto, todo)

    assert rw.repo.state() == RepositoryState.REBASE_INTERACTIVE
    assert rw.repo.head_commit_id == edit
    assert rw.mergeBanner.isVisible()
    assert findTextInWidget(rw.mergeBanner.label, "rebasing.+master.+onto.+" + str(onto)[:7])
    assert findTextInWidget(rw.mergeBanner.label, "stopped at.+" + str(edit)[:7])

    # Make some changes to the commit we're stopped at
    triggerMenuAction(mainWindow.menuBar(), "repo/amend")
    commitDialog = findQDialog(rw, "amend", t=CommitDialog)
    commitDialog.ui.summaryEditor.setText("Amended from Rebase")
    commitDialog.accept()

    # Continue rebasing
    continueButton = next(button for button in rw.mergeBanner.buttons
                          if findTextInWidget(button, "continue rebase"))
    continueButton.click()

    assert rw.repo.state() == RepositoryState.NONE
    assert not rw.mergeBanner.isVisible()
    assert rw.repo.head_commit_id != head, "new head must be different after making changes"


def testRebaseReword(tempDir, mainWindow):
    onto = Oid(hex="49322bb17d3acc9146f98c97d078513228bbf3c0")
    todo = [
        _Todo(0, RebaseOp.Reword, "rewording older commit"),
        _Todo(1, RebaseOp.Reword, "rewording newer commit"),
    ]

    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    _driveRebaseDialog(rw, onto, todo)

    assert rw.repo.state() == RepositoryState.NONE
    assert rw.repo.head_commit.message.strip() == "rewording newer commit"
    assert rw.repo.head_commit.parents[0].message.strip() == "rewording older commit"


def testRebaseRewordAfterContinue(tempDir, mainWindow):
    onto = Oid(hex="49322bb17d3acc9146f98c97d078513228bbf3c0")
    todo = [
        _Todo(0, RebaseOp.Edit),
        _Todo(1, RebaseOp.Reword, "rewording still works after continue"),
    ]

    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    _driveRebaseDialog(rw, onto, todo)

    assert rw.repo.state() == RepositoryState.REBASE_INTERACTIVE
    continueButton = next(button for button in rw.mergeBanner.buttons
                          if findTextInWidget(button, "continue rebase"))
    continueButton.click()

    assert rw.repo.state() == RepositoryState.NONE
    assert rw.repo.head_commit.message.strip() == "rewording still works after continue"
