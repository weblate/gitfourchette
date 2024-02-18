import pytest

from gitfourchette.nav import NavLocator
from . import reposcenario
from .util import *
from gitfourchette.sidebar.sidebarmodel import EItem
from gitfourchette.forms.newbranchdialog import NewBranchDialog
import re


@pytest.mark.parametrize("method", ["sidebar", "shortcut"])
def testNewBranch(tempDir, mainWindow, method):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    repo = rw.repo

    if method == "sidebar":
        node = next(rw.sidebar.findNodesByKind(EItem.LocalBranchesHeader))
        menu = rw.sidebar.makeNodeMenu(node)
        findMenuAction(menu, "new branch").trigger()
    elif method == "shortcut":
        QTest.keySequence(rw, "Ctrl+B")
    else:
        raise NotImplementedError("unknown method")

    q = findQDialog(rw, "new branch")
    q.findChild(QLineEdit).setText("hellobranch")
    q.accept()

    assert repo.branches.local['hellobranch'] is not None


def testSetUpstreamBranch(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    repo = rw.repo

    assert repo.branches.local['master'].upstream_name == "refs/remotes/origin/master"

    node = rw.sidebar.findNodeByRef("refs/heads/master")
    menu = rw.sidebar.makeNodeMenu(node)

    findMenuAction(menu, "(tracked|upstream) branch").trigger()

    # Change tracking from origin/master to nothing
    q = findQDialog(rw, "(tracked|upstream) branch")
    combobox: QComboBox = q.findChild(QComboBox)
    assert "origin/master" in combobox.currentText()
    assert re.match(r".*don.t track.*", combobox.itemText(0).lower())
    combobox.setCurrentIndex(0)
    q.accept()
    assert repo.branches.local['master'].upstream is None

    # Change tracking back to origin/master
    findMenuAction(menu, "(tracked|upstream) branch").trigger()
    q = findQDialog(rw, "(tracked|upstream) branch")
    combobox: QComboBox = q.findChild(QComboBox)
    assert re.match(r".*don.t track.*", combobox.currentText().lower())
    for i in range(combobox.count()):
        if "origin/master" in combobox.itemText(i):
            combobox.setCurrentIndex(i)
            break
    q.accept()

    assert repo.branches.local['master'].upstream == repo.branches.remote['origin/master']


def testRenameBranch(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    repo = rw.repo

    assert 'master' in repo.branches.local
    assert 'no-parent' in repo.branches.local
    assert 'mainbranch' not in repo.branches.local

    node = rw.sidebar.findNodeByRef("refs/heads/master")
    menu = rw.sidebar.makeNodeMenu(node)

    findMenuAction(menu, "rename").trigger()

    dlg = findQDialog(rw, "rename.+branch")
    nameEdit: QLineEdit = dlg.findChild(QLineEdit)
    okButton: QPushButton = dlg.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok)

    assert okButton
    assert okButton.isEnabled()

    nameEdit.setText("this-wont-pass-validation.lock")  # illegal suffix
    assert not okButton.isEnabled()

    nameEdit.setText("no-parent")  # already taken by another local branch
    assert not okButton.isEnabled()

    nameEdit.setText("")  # cannot be empty
    assert not okButton.isEnabled()

    nameEdit.setText("mainbranch")
    assert okButton.isEnabled()

    dlg.accept()

    assert 'master' not in repo.branches.local
    assert 'mainbranch' in repo.branches.local


def testDeleteBranch(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    with RepoContext(wd) as repo:
        commit = repo['6e1475206e57110fcef4b92320436c1e9872a322']
        repo.branches.create("somebranch", commit)
        assert "somebranch" in repo.branches.local

    rw = mainWindow.openRepo(wd)
    repo = rw.repo

    node = rw.sidebar.findNodeByRef("refs/heads/somebranch")
    menu = rw.sidebar.makeNodeMenu(node)
    triggerMenuAction(menu, "delete")
    acceptQMessageBox(rw, "really delete.+branch")
    assert "somebranch" not in repo.branches.local


def testDeleteCurrentBranch(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    repo = rw.repo

    assert "master" in repo.branches.local

    node = rw.sidebar.findNodeByRef("refs/heads/master")
    menu = rw.sidebar.makeNodeMenu(node)
    triggerMenuAction(menu, "delete")
    acceptQMessageBox(rw, "can.+t delete.+current branch")
    assert "master" in repo.branches.local  # still there


def testNewBranchTrackingRemoteBranch1(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    repo = rw.repo

    assert "newmaster" not in repo.branches.local

    node = rw.sidebar.findNodeByRef("refs/remotes/origin/master")
    menu = rw.sidebar.makeNodeMenu(node)
    triggerMenuAction(menu, "(start|new).+local branch")

    dlg: NewBranchDialog = findQDialog(rw, "new.+branch")
    dlg.ui.nameEdit.setText("newmaster")
    dlg.ui.upstreamCheckBox.setChecked(True)
    dlg.accept()

    assert repo.branches.local["newmaster"].upstream == repo.branches.remote["origin/master"]


def testNewBranchTrackingRemoteBranch2(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    repo = rw.repo

    node = rw.sidebar.findNodeByRef("refs/remotes/origin/first-merge")
    menu = rw.sidebar.makeNodeMenu(node)
    triggerMenuAction(menu, "(start|new).*local branch")

    dlg: NewBranchDialog = findQDialog(rw, "new.+branch")
    assert dlg.ui.nameEdit.text() == "first-merge"
    assert dlg.ui.upstreamCheckBox.isChecked()
    assert dlg.ui.upstreamComboBox.currentText() == "origin/first-merge"
    dlg.accept()

    localBranch = repo.branches.local['first-merge']
    assert localBranch
    assert localBranch.upstream_name == "refs/remotes/origin/first-merge"
    assert localBranch.target.hex == "0966a434eb1a025db6b71485ab63a3bfbea520b6"


@pytest.mark.parametrize("method", ["graphstart", "graphcheckout"])
def testNewBranchFromCommit(tempDir, mainWindow, method):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    localBranches = rw.repo.branches.local

    assert "first-merge" not in localBranches
    assert not any("first-merge" in n.data for n in rw.sidebar.findNodesByKind(EItem.LocalBranch))

    oid1 = Oid(hex="0966a434eb1a025db6b71485ab63a3bfbea520b6")
    rw.jump(NavLocator.inCommit(oid1))

    if method == "graphstart":
        triggerMenuAction(rw.graphView.makeContextMenu(), r"(start|new) branch")
    elif method == "graphcheckout":
        QTest.keyPress(rw.graphView, Qt.Key.Key_Return)
        qd = findQDialog(rw, r"check ?out")
        qd.findChild(QRadioButton, "createBranchRadioButton").setChecked(True)
        qd.accept()
    else:
        raise NotImplementedError("unknown method")

    dlg: NewBranchDialog = findQDialog(rw, "new branch")
    assert dlg.ui.nameEdit.text() == "first-merge"  # nameEdit should be pre-filled with name of a (remote) branch pointing to this commit
    dlg.ui.switchToBranchCheckBox.setChecked(True)
    dlg.accept()

    assert "first-merge" in localBranches
    assert localBranches["first-merge"].target == oid1
    assert localBranches["first-merge"].is_checked_out()
    assert any("first-merge" in n.data for n in rw.sidebar.findNodesByKind(EItem.LocalBranch))


@pytest.mark.parametrize("method", ["sidebar", "graphstart", "graphcheckout"])
def testNewBranchFromDetachedHead(tempDir, mainWindow, method):
    wd = unpackRepo(tempDir)
    oid = Oid(hex="f73b95671f326616d66b2afb3bdfcdbbce110b44")

    with RepoContext(wd) as repo:
        repo.checkout_commit(oid)
        assert repo.head_is_detached

    rw = mainWindow.openRepo(wd)
    localBranches = rw.repo.branches.local
    rw.jump(NavLocator.inCommit(oid))

    if method == "sidebar":
        node = next(rw.sidebar.findNodesByKind(EItem.DetachedHead))
        triggerMenuAction(rw.sidebar.makeNodeMenu(node), r"(start|new) branch")
    elif method == "graphstart":
        triggerMenuAction(rw.graphView.makeContextMenu(), r"(start|new) branch")
    elif method == "graphcheckout":
        QTest.keyPress(rw.graphView, Qt.Key.Key_Return)
        qd = findQDialog(rw, r"check ?out")
        qd.findChild(QRadioButton, "createBranchRadioButton").setChecked(True)
        qd.accept()
    else:
        raise NotImplementedError("unknown method")

    dlg: NewBranchDialog = findQDialog(rw, "new branch")
    dlg.ui.nameEdit.setText("coucou")
    dlg.ui.switchToBranchCheckBox.setChecked(True)
    dlg.accept()

    assert "coucou" in localBranches
    assert localBranches["coucou"].target == oid
    assert localBranches["coucou"].is_checked_out()
    assert any("coucou" in n.data for n in rw.sidebar.findNodesByKind(EItem.LocalBranch))



@pytest.mark.parametrize("method", ["sidebar", "graphstart", "graphcheckout"])
def testNewBranchFromLocalBranch(tempDir, mainWindow, method):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    localBranches = rw.repo.branches.local

    if method == "sidebar":
        node = rw.sidebar.findNodeByRef("refs/heads/no-parent")
        menu = rw.sidebar.makeNodeMenu(node)
        findMenuAction(menu, "new.+branch from here").trigger()
    elif method == "graphstart":
        rw.jump(NavLocator.inRef("refs/heads/no-parent"))
        triggerMenuAction(rw.graphView.makeContextMenu(), r"(start|new) branch")
    elif method == "graphcheckout":
        rw.jump(NavLocator.inRef("refs/heads/no-parent"))
        QTest.keyPress(rw.graphView, Qt.Key.Key_Return)
        qd = findQDialog(rw, r"check ?out")
        qd.findChild(QRadioButton, "createBranchRadioButton").setChecked(True)
        qd.accept()
    else:
        raise NotImplementedError("unknown method")

    dlg: NewBranchDialog = findQDialog(rw, "new.+branch")
    assert dlg.ui.nameEdit.text() == "no-parent-2"
    assert dlg.acceptButton.isEnabled()  # "no-parent-2" isn't taken

    dlg.ui.nameEdit.setText("no-parent")  # try to set a name that's taken
    assert not dlg.acceptButton.isEnabled()  # can't accept because branch name "no-parent" is taken

    dlg.ui.nameEdit.setText("no-parent-2")
    assert dlg.acceptButton.isEnabled()  # "no-parent-2" isn't taken
    dlg.accept()

    assert "no-parent-2" in localBranches
    assert localBranches["no-parent-2"].target == localBranches["no-parent"].target
    assert any("no-parent-2" in n.data for n in rw.sidebar.findNodesByKind(EItem.LocalBranch))


@pytest.mark.parametrize("method", ["sidebarmenu", "sidebarkey", "graphmenu", "graphkey"])
def testSwitchBranch(tempDir, mainWindow, method):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    localBranches = rw.repo.branches.local

    def getActiveBranchTooltipText():
        node = rw.sidebar.findNodeByRef(rw.repo.head_branch_fullname)
        index = node.createIndex(rw.sidebar.sidebarModel)
        tip = index.data(Qt.ItemDataRole.ToolTipRole)
        assert re.search(r"(current|checked.out) branch", tip, re.I)
        return tip

    # make sure initial branch state is correct
    assert localBranches['master'].is_checked_out()
    assert not localBranches['no-parent'].is_checked_out()
    assert os.path.isfile(f"{wd}/master.txt")
    assert os.path.isfile(f"{wd}/c/c1.txt")
    assert "master" in getActiveBranchTooltipText()
    assert "no-parent" not in getActiveBranchTooltipText()

    if method == "sidebarmenu":
        node = rw.sidebar.findNodeByRef("refs/heads/no-parent")
        menu = rw.sidebar.makeNodeMenu(node)
        triggerMenuAction(menu, "switch to")
    elif method == "sidebarkey":
        rw.sidebar.selectAnyRef("refs/heads/no-parent")
        QTest.keyPress(rw.sidebar, Qt.Key.Key_Return)
        acceptQMessageBox(rw, "switch to")
    elif method in ["graphmenu", "graphkey"]:
        rw.jump(NavLocator.inRef("refs/heads/no-parent"))
        if method == "graphmenu":
            triggerMenuAction(rw.graphView.makeContextMenu(), "check out")
        else:
            QTest.keyPress(rw.graphView, Qt.Key.Key_Return)
        qd = findQDialog(rw, "check out")
        assert qd.findChild(QRadioButton, "switchToLocalBranchRadioButton").isChecked()
        qd.accept()
    else:
        raise NotImplementedError("unknown method")

    assert not localBranches['master'].is_checked_out()
    assert localBranches['no-parent'].is_checked_out()
    assert not os.path.isfile(f"{wd}/master.txt")  # this file doesn't exist on the no-parent branch
    assert os.path.isfile(f"{wd}/c/c1.txt")

    # Active branch change should be reflected in sidebar UI
    assert "master" not in getActiveBranchTooltipText()
    assert "no-parent" in getActiveBranchTooltipText()


def testSwitchBranchWorkdirConflicts(tempDir, mainWindow):
    wd = unpackRepo(tempDir)

    writeFile(f"{wd}/c/c1.txt", "la menuiserie et toute la clique")

    rw = mainWindow.openRepo(wd)
    localBranches = rw.repo.branches.local

    assert not localBranches['no-parent'].is_checked_out()
    assert localBranches['master'].is_checked_out()

    node = rw.sidebar.findNodeByRef("refs/heads/no-parent")
    menu = rw.sidebar.makeNodeMenu(node)
    triggerMenuAction(menu, "switch to")

    acceptQMessageBox(rw, "conflict.+with.+file")  # this will fail if the messagebox doesn't show up

    assert not localBranches['no-parent'].is_checked_out()  # still not checked out
    assert localBranches['master'].is_checked_out()


def testMergeUpToDate(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)

    node = rw.sidebar.findNodeByRef("refs/remotes/origin/first-merge")
    menu = rw.sidebar.makeNodeMenu(node)
    triggerMenuAction(menu, "merge")
    acceptQMessageBox(rw, "already up.to.date")


def testMergeFastForward(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    with RepoContext(wd) as repo:
        repo.checkout_local_branch('no-parent')
    rw = mainWindow.openRepo(wd)

    assert rw.repo.head.target != rw.repo.branches.local['master'].target

    node = rw.sidebar.findNodeByRef("refs/heads/master")
    menu = rw.sidebar.makeNodeMenu(node)
    triggerMenuAction(menu, "merge")
    acceptQMessageBox(rw, "can .*fast.forward")

    assert rw.repo.head.target == rw.repo.branches.local['master'].target
