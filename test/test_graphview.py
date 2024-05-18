import pytest

from . import reposcenario
from .util import *
from gitfourchette.forms.commitdialog import CommitDialog
from gitfourchette.forms.prefsdialog import PrefsDialog
from gitfourchette.forms.unloadedrepoplaceholder import UnloadedRepoPlaceholder
from gitfourchette.nav import NavLocator, NavContext
from gitfourchette.sidebar.sidebarmodel import SidebarModel, SidebarNode, EItem


def testCommitSearch(tempDir, mainWindow):
    # Commits that contain "first" in their summary
    matchingCommits = [
        Oid(hex="6462e7d8024396b14d7651e2ec11e2bbf07a05c4"),
        Oid(hex="42e4e7c5e507e113ebbb7801b16b52cf867b7ce1"),
        Oid(hex="d31f5a60d406e831d056b8ac2538d515100c2df2"),
        Oid(hex="83d2f0431bcdc9c2fd2c17b828143be6ee4fbe80"),
        Oid(hex="2c349335b7f797072cf729c4f3bb0914ecb6dec9"),
        Oid(hex="ac7e7e44c1885efb472ad54a78327d66bfc4ecef"),
    ]

    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)

    searchBar = rw.graphView.searchBar
    searchEdit = searchBar.lineEdit

    def getGraphRow():
        indexes = rw.graphView.selectedIndexes()
        assert len(indexes) == 1
        return indexes[0].row()

    assert not searchBar.isVisibleTo(rw)

    QTest.qWait(0)
    QTest.keySequence(mainWindow, "Ctrl+F")
    assert searchBar.isVisibleTo(rw)

    QTest.keyClicks(searchEdit, "first")

    previousRow = -1
    for oid in matchingCommits:
        QTest.keySequence(searchEdit, "Return")
        QTest.qWait(0)  # Give event loop a breather (for code coverage in commitlogdelegate)
        assert oid == rw.graphView.currentCommitOid

        assert getGraphRow() > previousRow  # go down
        previousRow = getGraphRow()

    # end of log
    QTest.keySequence(searchEdit, "Return")
    assert getGraphRow() < previousRow  # wrap around to top of graph
    previousRow = getGraphRow()

    # select last
    lastRow = rw.graphView.clFilter.rowCount() - 1
    rw.graphView.setCurrentIndex(rw.graphView.clFilter.index(lastRow, 0))
    previousRow = lastRow

    # now search backwards
    for oid in reversed(matchingCommits):
        QTest.keySequence(searchEdit, "Shift+Return")
        assert oid == rw.graphView.currentCommitOid

        assert getGraphRow() < previousRow  # go up
        previousRow = getGraphRow()

    # top of log
    QTest.keySequence(searchEdit, "Shift+Return")
    assert getGraphRow() > previousRow
    previousRow = getGraphRow()

    # escape closes search bar
    QTest.keySequence(searchEdit, "Escape")
    assert not searchBar.isVisibleTo(rw)


def testCommitSearchByHash(tempDir, mainWindow):
    searchCommits = [
        Oid(hex="6462e7d8024396b14d7651e2ec11e2bbf07a05c4"),
        Oid(hex="42e4e7c5e507e113ebbb7801b16b52cf867b7ce1"),
        Oid(hex="d31f5a60d406e831d056b8ac2538d515100c2df2"),
        Oid(hex="83d2f0431bcdc9c2fd2c17b828143be6ee4fbe80"),
        Oid(hex="2c349335b7f797072cf729c4f3bb0914ecb6dec9"),
        Oid(hex="ac7e7e44c1885efb472ad54a78327d66bfc4ecef"),
    ]

    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)

    searchBar = rw.graphView.searchBar
    # In this unit test, we're also going to exercise the search bar's "pulse"
    # feature, i.e. start searching automatically when the user stops typing,
    # without hitting the Return key.
    # Normally, the search bar waits for a fraction of a second before emitting
    # the pulse. Make it "instantaneous" for the unit test.
    searchBar.searchPulseTimer.setInterval(0)
    searchEdit = searchBar.lineEdit

    assert not searchBar.isVisibleTo(rw)
    QTest.qWait(0)
    QTest.keySequence(mainWindow, "Ctrl+F")
    assert searchBar.isVisibleTo(rw)

    for j in range(2):  # first run in order, second run reversed
        for i in range(2):  # do it twice to make it wrap around
            for oid in searchCommits:
                searchEdit.selectAll()
                QTest.keyClicks(searchEdit, oid.hex[:5])
                QTest.qWait(0)  # Don't press enter and let it auto-search (pulse timer)
                assert oid == rw.graphView.currentCommitOid
        searchCommits.reverse()

    # Search for a bogus commit hash
    assert searchBar.property("red") == "false"
    searchEdit.selectAll()
    QTest.keyClicks(searchEdit, "aaabbcc")
    QTest.qWait(0)
    assert searchBar.property("red") == "true"  # QSS property that turns the text red
    # The pulse won't show an error message on its own.
    # Hit enter to bring up an error.
    QTest.keySequence(searchEdit, "Return")
    rejectQMessageBox(searchBar, "not found")


def testCommitSearchByAuthor(tempDir, mainWindow):
    # "A U Thor" has authored a ton of commits in the test repo, so take the first couple few
    searchCommits = [
        Oid(hex="c9ed7bf12c73de26422b7c5a44d74cfce5a8993b"),
        Oid(hex="ce112d052bcf42442aa8563f1e2b7a8aabbf4d17"),
        Oid(hex="49322bb17d3acc9146f98c97d078513228bbf3c0"),
    ]

    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)

    searchBar = rw.graphView.searchBar
    searchEdit = searchBar.lineEdit

    assert not searchBar.isVisibleTo(rw)
    QTest.qWait(0)
    QTest.keySequence(mainWindow, "Ctrl+F")
    assert searchBar.isVisibleTo(rw)
    QTest.keyClicks(searchEdit, "a u thor")

    for oid in searchCommits:
        QTest.keySequence(searchEdit, "Return")
        QTest.qWait(0)  # Give event loop a breather (for code coverage in commitlogdelegate)
        assert oid == rw.graphView.currentCommitOid


@pytest.mark.parametrize("method", ["hotkey", "contextmenu"])
def testCommitInfo(tempDir, mainWindow, method):
    oid1 = Oid(hex="83834a7afdaa1a1260568567f6ad90020389f664")
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    rw.jump(NavLocator.inCommit(oid1))

    if method == "hotkey":
        QTest.qWait(1)
        # Use Alt modifier to bring up debug info (for coverage)
        QTest.keyClick(rw.graphView, Qt.Key.Key_Space, Qt.KeyboardModifier.AltModifier)
    elif method == "contextmenu":
        triggerMenuAction(rw.graphView.makeContextMenu(), "get info")
    else:
        raise NotImplementedError(f"unknown method {method}")

    menu = rw.graphView.makeContextMenu()
    triggerMenuAction(menu, "get info")

    qmb = findQMessageBox(rw, "Merge branch 'a' into c")
    assert oid1.hex in qmb.text()
    assert "A U Thor" in qmb.text()
    qmb.accept()


@pytest.mark.parametrize("method", ["hotkey", "contextmenu"])
def testCopyCommitHash(tempDir, mainWindow, method):
    """
    WARNING: THIS TEST MODIFIES THE SYSTEM'S CLIPBOARD.
    """

    # Make sure the clipboard is clean before we begin
    QApplication.clipboard().clear()
    assert not QApplication.clipboard().text()

    oid1 = Oid(hex="83834a7afdaa1a1260568567f6ad90020389f664")
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    rw.jump(NavLocator.inCommit(oid1))

    if method == "hotkey":
        QTest.qWait(1)
        QTest.keySequence(rw.graphView, "Ctrl+C")
    elif method == "contextmenu":
        triggerMenuAction(rw.graphView.makeContextMenu(), "copy.+hash")
    else:
        raise NotImplementedError(f"unknown method {method}")

    QTest.qWait(1)
    assert QApplication.clipboard().text() == oid1.hex


def testRefSortFavorsHeadBranch(mainWindow, tempDir):
    masterOid = Oid(hex="c9ed7bf12c73de26422b7c5a44d74cfce5a8993b")

    wd = unpackRepo(tempDir)
    with RepoContext(wd) as repo:
        headCommit = repo.head_commit
        assert headCommit.oid == masterOid
        repo.create_branch_on_head("master-2")
        repo.checkout_local_branch("master-2")
        amendedOid = repo.amend_commit_on_head("should appear above master in graph", headCommit.author, headCommit.committer)
        assert repo[amendedOid].author.time == headCommit.author.time
        assert repo[amendedOid].committer.time == headCommit.committer.time

    rw = mainWindow.openRepo(wd)
    masterIndex = rw.graphView.getFilterIndexForCommit(masterOid)
    amendedIndex = rw.graphView.getFilterIndexForCommit(amendedOid)
    assert amendedIndex.row() < masterIndex.row()


def testCommitToolTip(mainWindow, tempDir):
    masterOid = Oid(hex="c9ed7bf12c73de26422b7c5a44d74cfce5a8993b")
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)

    oldCursorPos = QCursor.pos()

    mainWindow.resize(1500, 600)
    index = rw.graphView.selectRowForLocator(NavLocator.inCommit(masterOid))
    cursorPos = rw.graphView.mapToGlobal(QPoint(8, 8))
    QCursor.setPos(cursorPos)
    QTest.qWait(0)
    toolTip = index.data(Qt.ItemDataRole.ToolTipRole)
    assert not toolTip

    cursorPos = rw.graphView.mapToGlobal(QPoint(rw.graphView.width()-8, 8))
    QCursor.setPos(cursorPos)
    QTest.qWait(0)
    toolTip = index.data(Qt.ItemDataRole.ToolTipRole)
    assert "Delete c/c2-2.txt" not in toolTip
    assert "a.u.thor@example.com" in toolTip

    QCursor.setPos(oldCursorPos)
    mainWindow.resize(300, 600)
    QTest.qWait(0)
    toolTip = index.data(Qt.ItemDataRole.ToolTipRole)
    assert "Delete c/c2-2.txt" in toolTip
    assert "a.u.thor@example.com" in toolTip
