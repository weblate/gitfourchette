import re

from helpers.qttest_imports import *
from helpers import testutil
from helpers.fixtures import *
from widgets.remotedialog import RemoteDialog

from widgets.sidebar import SidebarEntryType


# TODO: Write test for switching


@withRepo("TestGitRepository")
@withPrep(None)
def testNewBranch(qtbot, workDirRepo, rw):
    menu = rw.sidebar.generateMenuForEntry(SidebarEntryType.LOCAL_BRANCHES_HEADER)
    testutil.findMenuAction(menu, "new branch").trigger()

    q = testutil.findQDialog(rw, "new branch")
    q.findChild(QLineEdit).setText("hellobranch")
    q.accept()

    newBranch: pygit2.Branch = workDirRepo.branches.local['hellobranch']
    assert newBranch is not None


@withRepo("TestGitRepository")
@withPrep(None)
def testCurrentBranchCannotSwitchMergeOrRebase(qtbot, workDirRepo, rw):
    menu = rw.sidebar.generateMenuForEntry(SidebarEntryType.LOCAL_BRANCH, "master")

    assert not testutil.findMenuAction(menu, "switch to").isEnabled()
    assert not testutil.findMenuAction(menu, "merge").isEnabled()
    assert not testutil.findMenuAction(menu, "rebase").isEnabled()


@withRepo("TestGitRepository")
@withPrep(None)
def testSetTrackedBranch(qtbot, workDirRepo, rw):
    assert workDirRepo.branches.local['master'].upstream_name == "refs/remotes/origin/master"

    menu = rw.sidebar.generateMenuForEntry(SidebarEntryType.LOCAL_BRANCH, "master")

    testutil.findMenuAction(menu, "tracked branch").trigger()

    # Change tracking from origin/master to nothing
    q = testutil.findQDialog(rw, "tracked branch")
    combobox: QComboBox = q.findChild(QComboBox)
    assert "origin/master" in combobox.currentText()
    assert re.match(r".*don.t track.*", combobox.itemText(0).lower())
    combobox.setCurrentIndex(0)
    q.accept()
    assert workDirRepo.branches.local['master'].upstream is None

    # Change tracking back to origin/master
    testutil.findMenuAction(menu, "tracked branch").trigger()
    q = testutil.findQDialog(rw, "tracked branch")
    combobox: QComboBox = q.findChild(QComboBox)
    assert re.match(r".*don.t track.*", combobox.currentText().lower())
    for i in range(combobox.count()):
        if "origin/master" in combobox.itemText(i):
            combobox.setCurrentIndex(i)
            break
    q.accept()

    assert workDirRepo.branches.local['master'].upstream == \
           workDirRepo.branches.remote['origin/master']


@withRepo("TestGitRepository")
@withPrep(None)
def testRenameBranch(qtbot, workDirRepo, rw):
    assert 'master' in workDirRepo.branches.local
    assert 'mainbranch' not in workDirRepo.branches.local

    menu = rw.sidebar.generateMenuForEntry(SidebarEntryType.LOCAL_BRANCH, "master")

    testutil.findMenuAction(menu, "rename").trigger()

    q = testutil.findQDialog(rw, "rename branch")
    q.findChild(QLineEdit).setText("mainbranch")
    q.accept()

    assert 'master' not in workDirRepo.branches.local
    assert 'mainbranch' in workDirRepo.branches.local


@withRepo("TestGitRepository")
@withPrep(None)
def testDeleteBranch(qtbot, workDirRepo, rw):
    commit = workDirRepo['6e1475206e57110fcef4b92320436c1e9872a322']
    workDirRepo.branches.create("somebranch", commit)
    assert "somebranch" in workDirRepo.branches.local

    menu = rw.sidebar.generateMenuForEntry(SidebarEntryType.LOCAL_BRANCH, "somebranch")
    testutil.findMenuAction(menu, "delete").trigger()
    testutil.acceptQMessageBox(rw, "delete branch")
    assert "somebranch" not in workDirRepo.branches.local


@withRepo("TestGitRepository")
@withPrep(None)
def testNewRemoteTrackingBranch(qtbot, workDirRepo, rw):
    assert "newmaster" not in workDirRepo.branches.local

    menu = rw.sidebar.generateMenuForEntry(SidebarEntryType.REMOTE_BRANCH, "origin/master")

    testutil.findMenuAction(menu, "new local branch tracking").trigger()

    q = testutil.findQDialog(rw, "new branch tracking")
    q.findChild(QLineEdit).setText("newmaster")
    q.accept()

    assert workDirRepo.branches.local["newmaster"].upstream == workDirRepo.branches.remote["origin/master"]


@withRepo("TestGitRepository")
@withPrep(None)
def testEditRemote(qtbot, workDirRepo, rw):
    # Ensure we're starting with the expected settings
    assert len(workDirRepo.remotes) == 1
    assert workDirRepo.remotes[0].name == "origin"

    menu = rw.sidebar.generateMenuForEntry(SidebarEntryType.REMOTE, "origin")

    testutil.findMenuAction(menu, "edit remote").trigger()

    q: RemoteDialog = testutil.findQDialog(rw, "edit remote")
    q.ui.nameEdit.setText("mainremote")
    q.ui.urlEdit.setText("https://127.0.0.1/example-repo.git")
    q.accept()

    assert len(workDirRepo.remotes) == 1
    assert workDirRepo.remotes[0].name == "mainremote"
    assert workDirRepo.remotes[0].url == "https://127.0.0.1/example-repo.git"


@withRepo("TestGitRepository")
@withPrep(None)
def testDeleteRemote(qtbot, workDirRepo, rw):
    assert workDirRepo.remotes["origin"] is not None

    menu = rw.sidebar.generateMenuForEntry(SidebarEntryType.REMOTE, "origin")

    testutil.findMenuAction(menu, "delete remote").trigger()
    testutil.acceptQMessageBox(rw, "delete remote")

    assert len(list(workDirRepo.remotes)) == 0

