# -----------------------------------------------------------------------------
# Copyright (C) 2026 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

from gitfourchette.forms.commitdialog import CommitDialog
from gitfourchette.forms.rebasedialog import RebaseDialog
from gitfourchette.nav import NavLocator
from .util import *


def _setUpRebase(rw, rebaseOntoOid, rebaseEditOid):
    rw.jump(NavLocator.inCommit(rebaseOntoOid, ""))

    with AsynchronousTaskContext(rw.taskRunner):
        # Bring up RebaseDialog
        triggerContextMenuAction(rw.graphView.viewport(), "rebase")
        rebaseDialog = waitForQDialog(rw, "rebase", t=RebaseDialog)

        # Select ce112d, mark it for editing
        row = next(row for row, item in enumerate(rebaseDialog.iterateAllItems())
                   if item.hexHash == str(rebaseEditOid))
        qlvClickNthRow(rebaseDialog.ui.commitList, row)
        QTest.keyPress(rebaseDialog.ui.commitList.viewport(), Qt.Key.Key_E)

        # Go ahead with the rebase
        rebaseDialog.accept()

    assert rw.repo.state() == RepositoryState.REBASE_INTERACTIVE
    assert rw.repo.head_commit_id == rebaseEditOid

    assert rw.mergeBanner.isVisible()
    assert findTextInWidget(rw.mergeBanner.label, "rebasing.+master.+onto.+" + str(rebaseOntoOid)[:7])
    assert findTextInWidget(rw.mergeBanner.label, "stopped at.+" + str(rebaseEditOid)[:7])


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
    headOid = Oid(hex="c9ed7bf12c73de26422b7c5a44d74cfce5a8993b")
    rebaseOntoOid = Oid(hex="49322bb17d3acc9146f98c97d078513228bbf3c0")
    rebaseEditOid = Oid(hex="ce112d052bcf42442aa8563f1e2b7a8aabbf4d17")

    wd = unpackRepo(tempDir)

    rw = mainWindow.openRepo(wd)
    _setUpRebase(rw, rebaseOntoOid, rebaseEditOid)

    # Abort the rebase
    abortButton = next(button for button in rw.mergeBanner.buttons
                       if findTextInWidget(button, "abort rebase"))
    abortButton.click()
    acceptQMessageBox(rw, "abort rebase")

    assert rw.repo.state() == RepositoryState.NONE
    assert not rw.mergeBanner.isVisible()
    assert rw.repo.head_commit_id == headOid


def testContinueRebase(tempDir, mainWindow):
    headOid = Oid(hex="c9ed7bf12c73de26422b7c5a44d74cfce5a8993b")
    rebaseOntoOid = Oid(hex="49322bb17d3acc9146f98c97d078513228bbf3c0")
    rebaseEditOid = Oid(hex="ce112d052bcf42442aa8563f1e2b7a8aabbf4d17")

    wd = unpackRepo(tempDir)

    rw = mainWindow.openRepo(wd)
    _setUpRebase(rw, rebaseOntoOid, rebaseEditOid)

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
    assert rw.repo.head_commit_id != headOid, "new head must be different after making changes"
