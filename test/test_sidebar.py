from . import reposcenario
from .fixtures import *
from .util import *
from gitfourchette.sidebar.sidebarmodel import EItem
from gitfourchette import porcelain


def testCurrentBranchCannotSwitchMergeOrRebase(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)

    menu = rw.sidebar.generateMenuForEntry(EItem.LocalBranch, "master")

    assert not findMenuAction(menu, "switch to").isEnabled()
    assert not findMenuAction(menu, "merge").isEnabled()
    assert not findMenuAction(menu, "rebase").isEnabled()


def testSidebarWithDetachedHead(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)

    with RepositoryContext(wd) as repo:
        porcelain.checkoutCommit(repo, pygit2.Oid(hex="7f822839a2fe9760f386cbbbcb3f92c5fe81def7"))

    rw = mainWindow.openRepo(wd)

    assert 1 == len(rw.sidebar.datasForItemType(EItem.DetachedHead))
    assert {'no-parent', 'master'} == set(rw.sidebar.datasForItemType(EItem.LocalBranch))

