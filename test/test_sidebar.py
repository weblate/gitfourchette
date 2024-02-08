from . import reposcenario
from .util import *
from gitfourchette.sidebar.sidebarmodel import EItem


def testCurrentBranchCannotSwitchOrMerge(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)

    node = rw.sidebar.findNodeByRef("refs/heads/master")
    menu = rw.sidebar.makeNodeMenu(node)

    assert not findMenuAction(menu, "switch to").isEnabled()
    assert not findMenuAction(menu, "merge").isEnabled()
    # assert not findMenuAction(menu, "rebase").isEnabled()


def testSidebarWithDetachedHead(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)

    with RepoContext(wd) as repo:
        repo.checkout_commit(Oid(hex="7f822839a2fe9760f386cbbbcb3f92c5fe81def7"))

    rw = mainWindow.openRepo(wd)

    headNode = rw.sidebar.findNodeByRef("HEAD")
    assert headNode.kind == EItem.DetachedHead
    assert [headNode] == list(rw.sidebar.findNodesByKind(EItem.DetachedHead))

    assert {'refs/heads/master', 'refs/heads/no-parent'
            } == set(n.data for n in rw.sidebar.findNodesByKind(EItem.LocalBranch))
