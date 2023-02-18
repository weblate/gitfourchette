from . import reposcenario
from .fixtures import *
from .util import *
from gitfourchette.widgets.sidebar import EItem
import re


def testNewBranch(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    repo = rw.repo

    menu = rw.sidebar.generateMenuForEntry(EItem.LocalBranchesHeader)
    findMenuAction(menu, "new branch").trigger()

    q = findQDialog(rw, "new branch")
    q.findChild(QLineEdit).setText("hellobranch")
    q.accept()

    assert repo.branches.local['hellobranch'] is not None


def testSetTrackedBranch(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    repo = rw.repo

    assert repo.branches.local['master'].upstream_name == "refs/remotes/origin/master"

    menu = rw.sidebar.generateMenuForEntry(EItem.LocalBranch, "master")

    findMenuAction(menu, "tracked branch").trigger()

    # Change tracking from origin/master to nothing
    q = findQDialog(rw, "tracked branch")
    combobox: QComboBox = q.findChild(QComboBox)
    assert "origin/master" in combobox.currentText()
    assert re.match(r".*don.t track.*", combobox.itemText(0).lower())
    combobox.setCurrentIndex(0)
    q.accept()
    assert repo.branches.local['master'].upstream is None

    # Change tracking back to origin/master
    findMenuAction(menu, "tracked branch").trigger()
    q = findQDialog(rw, "tracked branch")
    combobox: QComboBox = q.findChild(QComboBox)
    assert re.match(r".*don.t track.*", combobox.currentText().lower())
    for i in range(combobox.count()):
        if "origin/master" in combobox.itemText(i):
            combobox.setCurrentIndex(i)
            break
    q.accept()

    assert repo.branches.local['master'].upstream == repo.branches.remote['origin/master']


def testRenameBranch(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    repo = rw.repo

    assert 'master' in repo.branches.local
    assert 'mainbranch' not in repo.branches.local

    menu = rw.sidebar.generateMenuForEntry(EItem.LocalBranch, "master")

    findMenuAction(menu, "rename").trigger()

    q = findQDialog(rw, "rename.+branch")
    q.findChild(QLineEdit).setText("mainbranch")
    q.accept()

    assert 'master' not in repo.branches.local
    assert 'mainbranch' in repo.branches.local


def testDeleteBranch(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    repo = rw.repo

    commit = repo['6e1475206e57110fcef4b92320436c1e9872a322']
    repo.branches.create("somebranch", commit)
    assert "somebranch" in repo.branches.local

    menu = rw.sidebar.generateMenuForEntry(EItem.LocalBranch, "somebranch")
    findMenuAction(menu, "delete").trigger()
    acceptQMessageBox(rw, "really delete.+branch")
    assert "somebranch" not in repo.branches.local


def testNewRemoteTrackingBranch(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    repo = rw.repo

    assert "newmaster" not in repo.branches.local

    menu = rw.sidebar.generateMenuForEntry(EItem.RemoteBranch, "origin/master")

    findMenuAction(menu, "new local branch tracking").trigger()

    q = findQDialog(rw, "new branch tracking")
    q.findChild(QLineEdit).setText("newmaster")
    q.accept()

    assert repo.branches.local["newmaster"].upstream == repo.branches.remote["origin/master"]


def testNewRemoteTrackingBranch2(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    repo = rw.repo

    menu = rw.sidebar.generateMenuForEntry(EItem.RemoteBranch, "origin/first-merge")
    findMenuAction(menu, "new .*branch .*tracking").trigger()
    findQDialog(rw, "new .*branch .*tracking").accept()

    localBranch = repo.branches.local['first-merge']
    assert localBranch
    assert localBranch.upstream_name == "refs/remotes/origin/first-merge"
    assert localBranch.target.hex == "0966a434eb1a025db6b71485ab63a3bfbea520b6"


def testSwitchBranch(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)

    rw = mainWindow.openRepo(wd)
    localBranches = rw.repo.branches.local

    # make sure initial branch state is correct
    assert localBranches['master'].is_checked_out()
    assert not localBranches['no-parent'].is_checked_out()
    assert os.path.isfile(f"{wd}/master.txt")
    assert os.path.isfile(f"{wd}/c/c1.txt")

    menu = rw.sidebar.generateMenuForEntry(EItem.LocalBranch, 'no-parent')
    findMenuAction(menu, "switch to").trigger()

    assert not localBranches['master'].is_checked_out()
    assert localBranches['no-parent'].is_checked_out()
    assert not os.path.isfile(f"{wd}/master.txt")  # this file doesn't exist on the no-parent branch
    assert os.path.isfile(f"{wd}/c/c1.txt")
