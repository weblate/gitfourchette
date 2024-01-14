"""
Remote access tests.

Note: these tests don't actually access the network.
We use a bare repository on the local filesystem as a "remote server".
"""

from .util import *
from gitfourchette.sidebar.sidebarmodel import EItem
from gitfourchette import porcelain


def testFetchNewRemoteBranches(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    makeBareCopy(wd, addAsRemote="localfs", preFetch=False)
    rw = mainWindow.openRepo(wd)

    assert "localfs/master" not in rw.repo.branches.remote
    assert all(userData.startswith("origin/") for userData in rw.sidebar.datasForItemType(EItem.RemoteBranch))

    menu = rw.sidebar.generateMenuForEntry(EItem.Remote, "localfs")
    findMenuAction(menu, "fetch").trigger()

    assert "localfs/master" in rw.repo.branches.remote
    assert any(userData.startswith("localfs/") for userData in rw.sidebar.datasForItemType(EItem.RemoteBranch))


def testDeleteRemoteBranch(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    makeBareCopy(wd, addAsRemote="localfs", preFetch=True)
    rw = mainWindow.openRepo(wd)

    assert "localfs/no-parent" in rw.repo.branches.remote
    assert "localfs/no-parent" in rw.sidebar.datasForItemType(EItem.RemoteBranch)

    menu = rw.sidebar.generateMenuForEntry(EItem.RemoteBranch, "localfs/no-parent")
    findMenuAction(menu, "delete").trigger()
    acceptQMessageBox(rw, "really delete.+from.+remote repository")

    assert "localfs/no-parent" not in rw.repo.branches.remote
    assert "localfs/no-parent" not in rw.sidebar.datasForItemType(EItem.RemoteBranch)


def testFetchRemote(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)

    barePath = makeBareCopy(wd, addAsRemote="localfs", preFetch=True)

    # Make some modifications to the bare repository that serves as a remote.
    # We're going to create a new branch and delete another.
    # The client must pick up on those modifications once it fetches the remote.
    with RepoContext(barePath) as bareRepo:
        assert bareRepo.is_bare
        bareRepo.create_branch_on_head("new-remote-branch")
        bareRepo.delete_local_branch("no-parent")

    rw = mainWindow.openRepo(wd)

    # We only know about master and no-parent in the remote for now
    assert {"localfs/master", "localfs/no-parent"} == set(x for x in rw.repo.branches.remote if x.startswith("localfs/"))

    # Fetch the remote
    menu = rw.sidebar.generateMenuForEntry(EItem.Remote, "localfs")
    findMenuAction(menu, "fetch").trigger()

    # We must see that no-parent is gone and that new-remote-branch appeared
    assert {"localfs/master", "localfs/new-remote-branch"} == set(x for x in rw.repo.branches.remote if x.startswith("localfs/"))


def testFetchRemoteBranch(qtbot, tempDir, mainWindow):
    oldHead = Oid(hex="c9ed7bf12c73de26422b7c5a44d74cfce5a8993b")
    newHead = Oid(hex="6e1475206e57110fcef4b92320436c1e9872a322")

    wd = unpackRepo(tempDir)

    barePath = makeBareCopy(wd, addAsRemote="localfs", preFetch=True)

    # Modify the master branch in the bare repository that serves as a remote.
    # The client must pick up on this modification once it fetches the remote branch.
    with RepoContext(barePath) as bareRepo:
        assert bareRepo.is_bare
        assert bareRepo.head.target == oldHead
        bareRepo.reset_head2(newHead, mode="soft")  # can't reset hard in bare repos, whatever...
        assert bareRepo.head.target == newHead

    rw = mainWindow.openRepo(wd)

    # We still think the remote's master branch is on the old head for now
    assert rw.repo.branches.remote["localfs/master"].target == oldHead

    # Fetch the remote branch
    menu = rw.sidebar.generateMenuForEntry(EItem.RemoteBranch, "localfs/master")
    findMenuAction(menu, "fetch").trigger()

    # The position of the remote's master branch should be up-to-date now
    assert rw.repo.branches.remote["localfs/master"].target == newHead
