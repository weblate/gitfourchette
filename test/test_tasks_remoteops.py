from .fixtures import *
from .util import *
from gitfourchette.widgets.sidebar import EItem


def testFetchRemote(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    makeBareCopy(wd, addAsRemote=True)

    rw = mainWindow.openRepo(wd)

    assert all(userData.startswith("origin/") for userData in rw.sidebar.datasForItemType(EItem.RemoteBranch))

    menu = rw.sidebar.generateMenuForEntry(EItem.Remote, "localfs")
    findMenuAction(menu, "fetch").trigger()

    assert any(userData.startswith("localfs/") for userData in rw.sidebar.datasForItemType(EItem.RemoteBranch))
