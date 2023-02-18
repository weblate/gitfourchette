from .fixtures import *
from .util import *
from gitfourchette.widgets.sidebar import EItem


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


def testRenameRemoteBranch(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    makeBareCopy(wd, addAsRemote="localfs", preFetch=True)
    rw = mainWindow.openRepo(wd)

    assert "localfs/no-parent" in rw.repo.branches.remote
    assert any(userData == "localfs/no-parent" for userData in rw.sidebar.datasForItemType(EItem.RemoteBranch))

    menu = rw.sidebar.generateMenuForEntry(EItem.RemoteBranch, "localfs/no-parent")
    findMenuAction(menu, "rename").trigger()
    q = findQDialog(rw, "rename.+(remote.+branch|branch.+remote)")
    q.findChild(QLineEdit).setText("popo")
    q.accept()

    assert "localfs/popo" in rw.repo.branches.remote
    assert "localfs/no-parent" not in rw.repo.branches.remote

    assert "localfs/popo" in rw.sidebar.datasForItemType(EItem.RemoteBranch)
    assert "localfs/no-parent" not in rw.sidebar.datasForItemType(EItem.RemoteBranch)

