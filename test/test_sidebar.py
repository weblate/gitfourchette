from . import reposcenario
from .fixtures import *
from .util import *
from gitfourchette.widgets.remotedialog import RemoteDialog
from gitfourchette.widgets.sidebar import EItem
from gitfourchette.widgets.stashdialog import StashDialog
import re


# TODO: Write test for switching


@withRepo("TestGitRepository")
@withPrep(None)
def testNewBranch(qtbot, workDirRepo, rw):
    menu = rw.sidebar.generateMenuForEntry(EItem.LocalBranchesHeader)
    findMenuAction(menu, "new branch").trigger()

    q = findQDialog(rw, "new branch")
    q.findChild(QLineEdit).setText("hellobranch")
    q.accept()

    newBranch: pygit2.Branch = workDirRepo.branches.local['hellobranch']
    assert newBranch is not None


@withRepo("TestGitRepository")
@withPrep(None)
def testCurrentBranchCannotSwitchMergeOrRebase(qtbot, workDirRepo, rw):
    menu = rw.sidebar.generateMenuForEntry(EItem.LocalBranch, "master")

    assert not findMenuAction(menu, "switch to").isEnabled()
    assert not findMenuAction(menu, "merge").isEnabled()
    assert not findMenuAction(menu, "rebase").isEnabled()


@withRepo("TestGitRepository")
@withPrep(None)
def testSetTrackedBranch(qtbot, workDirRepo, rw):
    assert workDirRepo.branches.local['master'].upstream_name == "refs/remotes/origin/master"

    menu = rw.sidebar.generateMenuForEntry(EItem.LocalBranch, "master")

    findMenuAction(menu, "tracked branch").trigger()

    # Change tracking from origin/master to nothing
    q = findQDialog(rw, "tracked branch")
    combobox: QComboBox = q.findChild(QComboBox)
    assert "origin/master" in combobox.currentText()
    assert re.match(r".*don.t track.*", combobox.itemText(0).lower())
    combobox.setCurrentIndex(0)
    q.accept()
    assert workDirRepo.branches.local['master'].upstream is None

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

    assert workDirRepo.branches.local['master'].upstream == \
           workDirRepo.branches.remote['origin/master']


@withRepo("TestGitRepository")
@withPrep(None)
def testRenameBranch(qtbot, workDirRepo, rw):
    assert 'master' in workDirRepo.branches.local
    assert 'mainbranch' not in workDirRepo.branches.local

    menu = rw.sidebar.generateMenuForEntry(EItem.LocalBranch, "master")

    findMenuAction(menu, "rename").trigger()

    q = findQDialog(rw, "rename branch")
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

    menu = rw.sidebar.generateMenuForEntry(EItem.LocalBranch, "somebranch")
    findMenuAction(menu, "delete").trigger()
    acceptQMessageBox(rw, "delete branch")
    assert "somebranch" not in workDirRepo.branches.local


@withRepo("TestGitRepository")
@withPrep(None)
def testNewRemoteTrackingBranch(qtbot, workDirRepo, rw):
    assert "newmaster" not in workDirRepo.branches.local

    menu = rw.sidebar.generateMenuForEntry(EItem.RemoteBranch, "origin/master")

    findMenuAction(menu, "new local branch tracking").trigger()

    q = findQDialog(rw, "new branch tracking")
    q.findChild(QLineEdit).setText("newmaster")
    q.accept()

    assert workDirRepo.branches.local["newmaster"].upstream == workDirRepo.branches.remote["origin/master"]


@withRepo("TestGitRepository")
@withPrep(None)
def testNewRemote(qtbot, workDirRepo, rw):
    # Ensure we're starting with the expected settings
    assert len(workDirRepo.remotes) == 1
    assert workDirRepo.remotes[0].name == "origin"

    menu = rw.sidebar.generateMenuForEntry(EItem.RemotesHeader)

    findMenuAction(menu, "new remote").trigger()

    q: RemoteDialog = findQDialog(rw, "new remote")
    q.ui.nameEdit.setText("otherremote")
    q.ui.urlEdit.setText("https://127.0.0.1/example-repo.git")
    q.accept()

    assert len(workDirRepo.remotes) == 2
    assert workDirRepo.remotes[1].name == "otherremote"
    assert workDirRepo.remotes[1].url == "https://127.0.0.1/example-repo.git"


@withRepo("TestGitRepository")
@withPrep(None)
def testEditRemote(qtbot, workDirRepo, rw):
    # Ensure we're starting with the expected settings
    assert len(workDirRepo.remotes) == 1
    assert workDirRepo.remotes[0].name == "origin"

    menu = rw.sidebar.generateMenuForEntry(EItem.Remote, "origin")

    findMenuAction(menu, "edit remote").trigger()

    q: RemoteDialog = findQDialog(rw, "edit remote")
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

    menu = rw.sidebar.generateMenuForEntry(EItem.Remote, "origin")

    findMenuAction(menu, "delete remote").trigger()
    acceptQMessageBox(rw, "delete remote")

    assert len(list(workDirRepo.remotes)) == 0


def getEItemIndices(rw: RepoWidget, item: EItem):
    model: QAbstractItemModel = rw.sidebar.model()
    indexList: list[QModelIndex] = model.match(model.index(0, 0), Qt.UserRole + 1, item, flags=Qt.MatchRecursive)
    return indexList


@withRepo("TestGitRepository")
@withPrep(reposcenario.fileWithUnstagedChange)
def testNewStash(qtbot, workDirRepo, rw):
    assert len(workDirRepo.listall_stashes()) == 0

    assert len(getEItemIndices(rw, EItem.Stash)) == 0
    assert qlvGetRowData(rw.dirtyFiles) == ["a/a1.txt"]

    menu = rw.sidebar.generateMenuForEntry(EItem.StashesHeader)
    findMenuAction(menu, "new stash").trigger()

    dlg: StashDialog = findQDialog(rw, "new stash")
    dlg.ui.messageEdit.setText("helloworld")
    dlg.accept()

    stashIndices = getEItemIndices(rw, EItem.Stash)
    assert len(workDirRepo.listall_stashes()) == 1
    assert len(stashIndices) == 1
    assert stashIndices[0].data(Qt.DisplayRole).endswith("helloworld")
    assert qlvGetRowData(rw.dirtyFiles) == []


@withRepo("TestGitRepository")
@withPrep(reposcenario.stashedChange)
def testPopStash(qtbot, workDirRepo, rw):
    stashIndices = getEItemIndices(rw, EItem.Stash)
    assert len(stashIndices) == 1

    menu = rw.sidebar.generateMenuForEntry(EItem.Stash, stashIndices[0].data(Qt.UserRole))
    findMenuAction(menu, "^pop").trigger()

    stashIndices = getEItemIndices(rw, EItem.Stash)
    assert len(workDirRepo.listall_stashes()) == 0
    assert len(stashIndices) == 0
    assert qlvGetRowData(rw.dirtyFiles) == ["a/a1.txt"]


@withRepo("TestGitRepository")
@withPrep(reposcenario.stashedChange)
def testApplyStash(qtbot, workDirRepo, rw):
    stashIndices = getEItemIndices(rw, EItem.Stash)
    assert len(stashIndices) == 1

    menu = rw.sidebar.generateMenuForEntry(EItem.Stash, stashIndices[0].data(Qt.UserRole))
    findMenuAction(menu, r"^apply").trigger()

    stashIndices = getEItemIndices(rw, EItem.Stash)
    assert len(workDirRepo.listall_stashes()) == 1
    assert len(stashIndices) == 1
    assert qlvGetRowData(rw.dirtyFiles) == ["a/a1.txt"]


@withRepo("TestGitRepository")
@withPrep(reposcenario.stashedChange)
def testDropStash(qtbot, workDirRepo, rw):
    assert qlvGetRowData(rw.dirtyFiles) == []

    stashIndices = getEItemIndices(rw, EItem.Stash)
    assert len(stashIndices) == 1

    menu = rw.sidebar.generateMenuForEntry(EItem.Stash, stashIndices[0].data(Qt.UserRole))
    findMenuAction(menu, "^delete").trigger()

    stashIndices = getEItemIndices(rw, EItem.Stash)
    assert len(workDirRepo.listall_stashes()) == 0
    assert len(stashIndices) == 0
    assert qlvGetRowData(rw.dirtyFiles) == []
