from . import reposcenario
from .fixtures import *
from .util import *
from gitfourchette.widgets.repowidget import RepoWidget
from gitfourchette.widgets.remotedialog import RemoteDialog
from gitfourchette.widgets.sidebar import EItem
from gitfourchette.widgets.stashdialog import StashDialog
import re


# TODO: Write test for switching


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


def testCurrentBranchCannotSwitchMergeOrRebase(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)

    menu = rw.sidebar.generateMenuForEntry(EItem.LocalBranch, "master")

    assert not findMenuAction(menu, "switch to").isEnabled()
    assert not findMenuAction(menu, "merge").isEnabled()
    assert not findMenuAction(menu, "rebase").isEnabled()


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

    q = findQDialog(rw, "rename branch")
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
    acceptQMessageBox(rw, "delete branch")
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


def testNewRemote(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    repo = rw.repo

    # Ensure we're starting with the expected settings
    assert len(repo.remotes) == 1
    assert repo.remotes[0].name == "origin"

    menu = rw.sidebar.generateMenuForEntry(EItem.RemotesHeader)

    findMenuAction(menu, "new remote").trigger()

    q: RemoteDialog = findQDialog(rw, "new remote")
    q.ui.nameEdit.setText("otherremote")
    q.ui.urlEdit.setText("https://127.0.0.1/example-repo.git")
    q.accept()

    assert len(repo.remotes) == 2
    assert repo.remotes[1].name == "otherremote"
    assert repo.remotes[1].url == "https://127.0.0.1/example-repo.git"


def testEditRemote(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    repo = rw.repo

    # Ensure we're starting with the expected settings
    assert len(repo.remotes) == 1
    assert repo.remotes[0].name == "origin"

    menu = rw.sidebar.generateMenuForEntry(EItem.Remote, "origin")

    findMenuAction(menu, "edit remote").trigger()

    q: RemoteDialog = findQDialog(rw, "edit remote")
    q.ui.nameEdit.setText("mainremote")
    q.ui.urlEdit.setText("https://127.0.0.1/example-repo.git")
    q.accept()

    assert len(repo.remotes) == 1
    assert repo.remotes[0].name == "mainremote"
    assert repo.remotes[0].url == "https://127.0.0.1/example-repo.git"


def testDeleteRemote(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    repo = rw.repo

    assert repo.remotes["origin"] is not None

    menu = rw.sidebar.generateMenuForEntry(EItem.Remote, "origin")

    findMenuAction(menu, "delete remote").trigger()
    acceptQMessageBox(rw, "delete remote")

    assert len(list(repo.remotes)) == 0


def getEItemIndices(rw: RepoWidget, item: EItem):
    model: QAbstractItemModel = rw.sidebar.model()
    indexList: list[QModelIndex] = model.match(model.index(0, 0), Qt.UserRole + 1, item, flags=Qt.MatchRecursive)
    return indexList


def testNewStash(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    writeFile(F"{wd}/a/a1.txt", "a1\nPENDING CHANGE\n")  # unstaged change
    rw = mainWindow.openRepo(wd)
    repo = rw.repo

    assert len(repo.listall_stashes()) == 0

    assert len(getEItemIndices(rw, EItem.Stash)) == 0
    assert qlvGetRowData(rw.dirtyFiles) == ["a/a1.txt"]

    menu = rw.sidebar.generateMenuForEntry(EItem.StashesHeader)
    findMenuAction(menu, "new stash").trigger()

    dlg: StashDialog = findQDialog(rw, "new stash")
    dlg.ui.messageEdit.setText("helloworld")
    dlg.accept()

    stashIndices = getEItemIndices(rw, EItem.Stash)
    assert len(repo.listall_stashes()) == 1
    assert len(stashIndices) == 1
    assert stashIndices[0].data(Qt.DisplayRole).endswith("helloworld")
    assert qlvGetRowData(rw.dirtyFiles) == []


def testPopStash(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    reposcenario.stashedChange(wd)
    rw = mainWindow.openRepo(wd)
    repo = rw.repo

    stashIndices = getEItemIndices(rw, EItem.Stash)
    assert len(stashIndices) == 1

    menu = rw.sidebar.generateMenuForEntry(EItem.Stash, stashIndices[0].data(Qt.UserRole))
    findMenuAction(menu, "^pop").trigger()

    stashIndices = getEItemIndices(rw, EItem.Stash)
    assert len(repo.listall_stashes()) == 0
    assert len(stashIndices) == 0
    assert qlvGetRowData(rw.dirtyFiles) == ["a/a1.txt"]


def testApplyStash(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    reposcenario.stashedChange(wd)
    rw = mainWindow.openRepo(wd)
    repo = rw.repo

    stashIndices = getEItemIndices(rw, EItem.Stash)
    assert len(stashIndices) == 1

    menu = rw.sidebar.generateMenuForEntry(EItem.Stash, stashIndices[0].data(Qt.UserRole))
    findMenuAction(menu, r"^apply").trigger()

    stashIndices = getEItemIndices(rw, EItem.Stash)
    assert len(repo.listall_stashes()) == 1
    assert len(stashIndices) == 1
    assert qlvGetRowData(rw.dirtyFiles) == ["a/a1.txt"]


def testDropStash(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    reposcenario.stashedChange(wd)
    rw = mainWindow.openRepo(wd)
    repo = rw.repo

    assert qlvGetRowData(rw.dirtyFiles) == []

    stashIndices = getEItemIndices(rw, EItem.Stash)
    assert len(stashIndices) == 1

    menu = rw.sidebar.generateMenuForEntry(EItem.Stash, stashIndices[0].data(Qt.UserRole))
    findMenuAction(menu, "^delete").trigger()

    stashIndices = getEItemIndices(rw, EItem.Stash)
    assert len(repo.listall_stashes()) == 0
    assert len(stashIndices) == 0
    assert qlvGetRowData(rw.dirtyFiles) == []


def testNewTrackingBranch(qtbot, tempDir, mainWindow):
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
