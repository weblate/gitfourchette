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
from gitfourchette.rebase.rebasesequencestyle import RebaseSequenceStyle
from gitfourchette.rebase.rebasesequenceview import RebaseSequenceView
from gitfourchette.toolbox import QRichTextMenu
from .util import *


@dataclasses.dataclass
class _Todo:
    row: int
    op: RebaseOp
    message: str = ""


def _driveRebaseDialog(rw, onto: Oid, todoList: list[_Todo]):
    rw.jump(NavLocator.inCommit(onto, ""))

    # Bring up RebaseDialog
    triggerContextMenuAction(rw.graphView.viewport(), "rebase")
    rebaseDialog = waitForQDialog(rw, "rebase", t=RebaseDialog)

    sequenceView = rebaseDialog.ui.sequence

    # Apply all operations
    for todo in todoList:
        sequenceView.setFocus()
        waitUntilTrue(sequenceView.hasFocus)

        # Select row
        bottomUpRow = sequenceView.model().rowCount() - 1 - todo.row
        qlvClickNthRow(sequenceView, bottomUpRow)

        # Press keyboard shortcut for desired operation
        QTest.keyClicks(sequenceView.viewport(), RebaseOpLetters[todo.op])

        itemsSoFar = sequenceView.allRebaseLines()
        assert itemsSoFar[todo.row].op == todo.op

        # Apply reworded message, if any
        if todo.message:
            assert todo.op.isEditable(), "need editable op to change message"

            # QLineEdit should have been brought up by hotkey
            lineEdit: QLineEdit = sequenceView.findChild(QLineEdit)
            assert lineEdit is not None
            assert lineEdit.hasFocus()
            assert lineEdit.isVisible()

            # Fill it in
            QTest.keyClicks(lineEdit, todo.message)

            # Warning: in real life, Return commits the current text in the
            # QLineEdit, but in offscreen mode, this accepts the entire dialog.
            lineEdit.clearFocus()
            QTest.qWait(0)

    return rebaseDialog


@pytest.mark.parametrize("withChanges", [False, True], ids=["no changes", "with changes"])
def testCancelRebaseDialog(tempDir, mainWindow, withChanges):
    wd = unpackRepo(tempDir)

    rw = mainWindow.openRepo(wd)
    rw.jump(NavLocator.inCommit(Oid(hex="49322bb17d3acc9146f98c97d078513228bbf3c0"), "a/a1"), check=True)

    onto = Oid(hex="49322bb17d3acc9146f98c97d078513228bbf3c0")
    todo = [_Todo(0, RebaseOp.Edit)] if withChanges else []

    rebaseDialog = _driveRebaseDialog(rw, onto, todo)
    rebaseDialog.reject()

    if withChanges:
        assert rebaseDialog.isVisible()
        qmb = findQMessageBox(rebaseDialog, "really close")
        findWidgetWithText(qmb.buttons(), "close").click()

    assert rw.repo.state() == RepositoryState.NONE


def testAbortRebase(tempDir, mainWindow):
    head = Oid(hex="c9ed7bf12c73de26422b7c5a44d74cfce5a8993b")
    onto = Oid(hex="49322bb17d3acc9146f98c97d078513228bbf3c0")
    edit = Oid(hex="ce112d052bcf42442aa8563f1e2b7a8aabbf4d17")
    todo = [_Todo(0, RebaseOp.Edit)]

    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    _driveRebaseDialog(rw, onto, todo).accept()

    assert rw.repo.state() == RepositoryState.REBASE_INTERACTIVE
    assert rw.repo.head_commit_id == edit
    assert rw.mergeBanner.isVisible()
    assert findTextInWidget(rw.mergeBanner.label, "rebasing.+master.+onto.+" + str(onto)[:7])
    assert findTextInWidget(rw.mergeBanner.label, "stopped at.+" + str(edit)[:7])

    # Abort the rebase
    findWidgetWithText(rw.mergeBanner.buttons, "abort rebase").click()
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
    _driveRebaseDialog(rw, onto, todo).accept()

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
    continueButton = rw.mergeBanner.findButton("continue rebase")
    assert continueButton.isEnabled()
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
    _driveRebaseDialog(rw, onto, todo).accept()

    assert rw.repo.state() == RepositoryState.NONE
    assert rw.repo.head_commit.message.strip() == "rewording newer commit"
    assert rw.repo.head_commit.parents[0].message.strip() == "rewording older commit"


def testRebaseRewordDisplayMessage(tempDir, mainWindow):
    onto = Oid(hex="49322bb17d3acc9146f98c97d078513228bbf3c0")
    todo = [
        _Todo(0, RebaseOp.Reword, "hello rewording"),
    ]

    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    dialog = _driveRebaseDialog(rw, onto, todo)

    def getSelectedMessage():
        return dialog.ui.sequence.selectedRebaseLines()[0].displayMessage()

    # Switching from 'reword' to 'pick' should revert the old name
    qlvClickNthRow(dialog.ui.sequence, 1)
    assert "hello rewording" == getSelectedMessage()
    QTest.keyClicks(dialog.ui.sequence.viewport(), RebaseOpLetters[RebaseOp.Pick])
    assert "Rename c/c2.txt => c/c2-2.txt" == getSelectedMessage()

    # Switching back to 'reword' should have saved the message that we entered originally
    QTest.keyClicks(dialog.ui.sequence.viewport(), RebaseOpLetters[RebaseOp.Reword])
    assert "hello rewording" == getSelectedMessage()

    dialog.accept()


def testRebaseRewordAfterContinue(tempDir, mainWindow):
    onto = Oid(hex="49322bb17d3acc9146f98c97d078513228bbf3c0")
    todo = [
        _Todo(0, RebaseOp.Edit),
        _Todo(1, RebaseOp.Reword, "rewording still works after continue"),
    ]

    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    _driveRebaseDialog(rw, onto, todo).accept()

    assert rw.repo.state() == RepositoryState.REBASE_INTERACTIVE
    assert rw.mergeBanner.isVisible()
    continueButton = rw.mergeBanner.findButton("continue rebase")
    assert continueButton.isEnabled()
    continueButton.click()

    assert rw.repo.state() == RepositoryState.NONE
    assert rw.repo.head_commit.message.strip() == "rewording still works after continue"


def testRebaseCausesConflicts(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    shell("""
        git rm master.txt
        git commit -am 'deleting master.txt'

        git branch hello2 49322bb17d3acc9146f98c97d078513228bbf3c0
        git checkout hello2

        echo 'bump' > c/c2.txt
        git commit -am 'modifying c/c2.txt'

        echo 'bump' > master.txt
        git commit -am 'modifying master.txt'
    """, wd)

    onto = Oid(hex="653b7d48ae91074764e7ae41449c8d0942e640a6")
    todo = []

    rw = mainWindow.openRepo(wd)
    _driveRebaseDialog(rw, onto, todo).accept()

    assert rw.repo.state() == RepositoryState.REBASE_INTERACTIVE
    assert rw.mergeBanner.isVisible()

    # Rebase blocked by conflict
    for stoppedAt, conflictFile in [
        ("f044e03", "c/c2.txt"),   # first iteration: task InteractiveRebase gets stopped
        ("5aba9ee", "master.txt"),  # second iteration: task ContinueRebase gets stopped
    ]:
        assert findTextInWidget(rw.mergeBanner.label, "stopped at.+" + stoppedAt)
        assert findTextInWidget(rw.mergeBanner.label, "fix conflicts to continue")

        # Continue button should be grayed out
        continueButton = rw.mergeBanner.findButton("continue rebase")
        assert not continueButton.isEnabled()

        # Task should auto-jump to 1st conflict
        assert NavLocator.inUnstaged(conflictFile).isSimilarEnoughTo(rw.navLocator)

        # Resolve the conflict
        assert rw.conflictView.isVisible()
        assert rw.conflictView.ui.oursButton.isVisible()
        assert rw.conflictView.ui.theirsButton.isVisible()
        assert findTextInWidget(rw.conflictView.ui.oursButton, "keep our deletion")
        assert findTextInWidget(rw.conflictView.ui.theirsButton, "accept their version")
        rw.conflictView.ui.theirsButton.click()
        acceptQMessageBox(rw, "accept their")

        # Continue rebase
        continueButton = rw.mergeBanner.findButton("continue rebase")
        assert continueButton.isEnabled()
        continueButton.click()

    assert not rw.mergeBanner.isVisible()
    assert rw.repo.state() == RepositoryState.NONE
    assert rw.repo.head_commit.message.startswith("modifying master.txt")
    assert rw.repo.head_commit.parents[0].message.startswith("modifying c/c2.txt")


def testRebaseNoopDud(tempDir, mainWindow):
    shell("""
        git init repo -b master
        cd repo
        git commit --allow-empty -m 'root commit'
    """, tempDir.name)

    wd = f"{tempDir.name}/repo"
    onto = readOidFile(f"{wd}/.git/refs/heads/master")

    rw = mainWindow.openRepo(wd)
    rw.jump(NavLocator.inCommit(onto, ""), check=True)

    triggerContextMenuAction(rw.graphView.viewport(), "rebase")
    acceptQMessageBox(rw, "no rebase is necessary")
    assert rw.repo.branches.local["master"].target == onto


def testRebaseNoopReset(tempDir, mainWindow):
    shell("""
        git init -b master repo
        cd repo
        touch hello.txt
        git add hello.txt
        git commit -m 'root commit'
        echo 'hello' > hello.txt
        git commit -am 'add some text'
        git branch rebase-onto-here
        git commit --amend -m 'add exact same text with a different commit message'
    """, tempDir.name)

    wd = f"{tempDir.name}/repo"
    onto = readOidFile(f"{wd}/.git/refs/heads/rebase-onto-here")
    rw = mainWindow.openRepo(wd)
    rw.jump(NavLocator.inCommit(onto, "hello.txt"), check=True)

    triggerContextMenuAction(rw.graphView.viewport(), "rebase")
    acceptQMessageBox(rw, "all commits from.+master.+are already in the other branch")
    visualPause()
    assert rw.repo.branches.local["master"].target == onto


def testRebasePlanOutOfSync(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    onto = Oid(hex="49322bb17d3acc9146f98c97d078513228bbf3c0")
    todo = []

    rw = mainWindow.openRepo(wd)
    rebaseDialog = _driveRebaseDialog(rw, onto, todo)

    shell("git checkout ce112d0", wd)
    rw.refreshRepo()

    rebaseDialog.accept()
    rejectQMessageBox(rw, "cannot apply this rebase plan")


def testRebaseVerifyEmptyCommitsInTodo(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    shell("""
        git commit --allow-empty -m 'some dummy commit'

        echo 'yoink' > master.txt
        git commit -am 'gotcha # empty'
    """, wd)

    onto = Oid(hex="49322bb17d3acc9146f98c97d078513228bbf3c0")
    todo = []

    rw = mainWindow.openRepo(wd)
    rebaseDialog = _driveRebaseDialog(rw, onto, todo)
    seq = rebaseDialog.initialSequence

    assert seq[-2].originalComment == "some dummy commit # empty"
    assert seq[-2].displayMessage() == "some dummy commit"
    assert seq[-2].verifiedEmpty

    assert seq[-1].originalComment == "gotcha # empty"
    assert seq[-1].displayMessage() == "gotcha # empty"
    assert not seq[-1].verifiedEmpty

    rebaseDialog.reject()


def testRebaseBannerCantContinueWithUnstagedChanges(tempDir, mainWindow):
    onto = Oid(hex="49322bb17d3acc9146f98c97d078513228bbf3c0")
    todo = [_Todo(0, RebaseOp.Edit)]

    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    banner = rw.mergeBanner
    _driveRebaseDialog(rw, onto, todo).accept()

    assert findTextInWidget(banner.label, "you can continue")
    assert banner.isVisible()
    assert banner.property("heeded") == "true"
    assert banner.findButton("continue rebase").isEnabled()

    writeFile(f"{wd}/master.txt", "hello")
    rw.refreshRepo()
    assert findTextInWidget(banner.label, "stage.+your changes to continue")
    assert banner.property("heeded") != "true"
    assert not banner.findButton("continue rebase").isEnabled()

    rw.jump(NavLocator.inUnstaged("master.txt"), check=True)
    rw.diffArea.stageButton.click()
    assert findTextInWidget(banner.label, "you can continue")
    assert banner.property("heeded") == "true"
    assert banner.findButton("continue rebase").isEnabled()
    banner.findButton("continue rebase").click()


def testRebaseSequenceStyleDropIndicator(tempDir, mainWindow, monkeypatch):
    """
    Coverage test for the custom drop indicator painting code in
    RebaseSequenceStyle.

    QDragEnterEvent/QDragMoveEvent/QDropEvent work with MIME data, but Qt won't
    preserve our custom data via MIME drag-and-drop. To avoid corrupting the
    list, we don't actually complete the drop in this coverage test
    (QDragLeaveEvent instead of QDropEvent).
    """

    callSpy = CallSpy(monkeypatch, RebaseSequenceStyle, "drawDropIndicator")

    wd = unpackRepo(tempDir)
    onto = Oid(hex="42e4e7c5e507e113ebbb7801b16b52cf867b7ce1")

    rw = mainWindow.openRepo(wd)

    # Bring up RebaseDialog
    rw.jump(NavLocator.inCommit(onto, ""))
    triggerContextMenuAction(rw.graphView.viewport(), "rebase")
    rebaseDialog = waitForQDialog(rw, "rebase", t=RebaseDialog)

    view: RebaseSequenceView = rebaseDialog.ui.sequence
    LMB = Qt.MouseButton.LeftButton
    MOD = Qt.KeyboardModifier.NoModifier
    ps = qlvVisualRect(view, 4).center()
    pd = qlvVisualRect(view, 0).center()

    qlvClickNthRow(view, 4)
    mime = view.model().mimeData(view.selectedIndexes())

    events = [
        QDragEnterEvent(ps, Qt.DropAction.MoveAction, mime, LMB, MOD),
        QDragMoveEvent(pd, Qt.DropAction.MoveAction, mime, LMB, MOD),
        QDragLeaveEvent(),  # leave instead of drop to avoid corrupting the list (see docstring)
    ]
    for e in events:
        QApplication.sendEvent(view.viewport(), e)
        QTest.qWait(0)
        assert e.isAccepted()
        visualPause(.5)

    assert callSpy.completeCalls >= 1

    rebaseDialog.reject()


@pytest.mark.skipif(QT5, reason="Qt 5 (deprecated) is finicky with this test, but Qt 6 is fine")
def testRebaseSequenceViewQDrag(tempDir, mainWindow, monkeypatch):
    """
    Coverage test for the custom QDrag in RebaseSequenceView.
    NOTE: Flaky on Wayland in non-offscreen mode.
    """

    callSpyMakeQDrag = CallSpy(monkeypatch, RebaseSequenceView, "makeQDrag")
    callSpyStartDrag = CallSpy(monkeypatch, RebaseSequenceView, "startDrag")

    wd = unpackRepo(tempDir)
    onto = Oid(hex="42e4e7c5e507e113ebbb7801b16b52cf867b7ce1")

    rw = mainWindow.openRepo(wd)

    # Bring up RebaseDialog
    rw.jump(NavLocator.inCommit(onto, ""))
    triggerContextMenuAction(rw.graphView.viewport(), "rebase")
    rebaseDialog = waitForQDialog(rw, "rebase", t=RebaseDialog)

    view = rebaseDialog.ui.sequence
    LMB = Qt.MouseButton.LeftButton
    ps = qlvVisualRect(view, 4).center()  # "On master again"

    # In offscreen mode, startDrag() returns immediately, so we can't actually
    # complete a move this way.
    allowActualMove = not OFFSCREEN
    if allowActualMove:
        pd = QPoint(ps.x(), 2)  # move to the top
    else:
        pd = ps + QPoint(100, 0)  # stay on same row

    clickTarget = view.viewport()

    QCursor.setPos(clickTarget.mapToGlobal(ps))
    QTest.mousePress(clickTarget, LMB, pos=ps)
    QCursor.setPos(clickTarget.mapToGlobal(pd))
    # In non-offscreen mode, startDrag() blocks the event loop, so schedule move
    # and release for later.
    QTimer.singleShot(0, lambda: QTest.mouseMove(clickTarget, pos=pd))
    QTimer.singleShot(500, lambda: QTest.mouseRelease(clickTarget, LMB, pos=pd))

    pause(1)
    assert callSpyMakeQDrag.completeCalls == 1
    assert callSpyStartDrag.completeCalls == 1

    rebaseDialog.reject()

    # If we did complete the move, RebaseDialog wants us to confirm closing a
    # modified rebase plan.
    if allowActualMove:
        assert rebaseDialog.ui.sequence.allRebaseLines()[0].displayMessage() == "On master again"
        qmb = findQMessageBox(rebaseDialog, "really close this rebase plan")
        findWidgetWithText(qmb.buttons(), "close").click()


def testRebaseRichTextMenu(tempDir, mainWindow, monkeypatch):
    """
    Coverage test for RebaseMenuStyle (colored labels).
    """

    callSpy = CallSpy(monkeypatch, QRichTextMenu, "paintEvent")

    wd = unpackRepo(tempDir)
    onto = Oid(hex="42e4e7c5e507e113ebbb7801b16b52cf867b7ce1")

    rw = mainWindow.openRepo(wd)

    # Bring up RebaseDialog
    rw.jump(NavLocator.inCommit(onto, ""))
    triggerContextMenuAction(rw.graphView.viewport(), "rebase")
    rebaseDialog = waitForQDialog(rw, "rebase", t=RebaseDialog)

    rebaseDialog.ui.sequence.setFocus()
    qlvClickNthRow(rebaseDialog.ui.sequence, 1)
    menu = summonContextMenu(rebaseDialog.ui.sequence.viewport(), QPoint(8, 8))
    visualPause()
    menu.close()

    assert callSpy.completeCalls > 0

    rebaseDialog.close()


def testRebaseJumpToCommit(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    onto = Oid(hex="42e4e7c5e507e113ebbb7801b16b52cf867b7ce1")
    head = Oid(hex="c9ed7bf12c73de26422b7c5a44d74cfce5a8993b")

    rw = mainWindow.openRepo(wd)

    # Bring up RebaseDialog
    rw.jump(NavLocator.inCommit(onto, ""))
    triggerContextMenuAction(rw.graphView.viewport(), "rebase")
    rebaseDialog = waitForQDialog(rw, "rebase", t=RebaseDialog)

    rebaseDialog.ui.sequence.setFocus()
    qlvClickNthRow(rebaseDialog.ui.sequence, 0)
    triggerContextMenuAction(rebaseDialog.ui.sequence.viewport(), "view commit in repo")

    visualPause()
    assert NavLocator.inCommit(head, "c/c2-2.txt").isSimilarEnoughTo(rw.navLocator)

    rebaseDialog.close()

