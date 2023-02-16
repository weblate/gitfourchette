from . import reposcenario
from .fixtures import *
from .util import *
from gitfourchette.widgets.repowidget import RepoWidget
from gitfourchette.widgets.remotedialog import RemoteDialog
from gitfourchette.widgets.sidebar import EItem
from gitfourchette.widgets.stashdialog import StashDialog
from gitfourchette import porcelain
import re


def testCurrentBranchCannotSwitchMergeOrRebase(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)

    menu = rw.sidebar.generateMenuForEntry(EItem.LocalBranch, "master")

    assert not findMenuAction(menu, "switch to").isEnabled()
    assert not findMenuAction(menu, "merge").isEnabled()
    assert not findMenuAction(menu, "rebase").isEnabled()


def testSidebarWithDetachedHead(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)

    repo = pygit2.Repository(wd)
    porcelain.checkoutCommit(repo, pygit2.Oid(hex="7f822839a2fe9760f386cbbbcb3f92c5fe81def7"))
    repo.free()  # necessary for correct test teardown on Windows
    del repo

    rw = mainWindow.openRepo(wd)

    indices = rw.sidebar.indicesForItemType(EItem.DetachedHead)
    assert len(indices) == 1

    indices = rw.sidebar.indicesForItemType(EItem.LocalBranch)
    assert len(indices) == 1

