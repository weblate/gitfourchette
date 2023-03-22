from gitfourchette.nav import NavContext, NavLocator
from . import reposcenario
from .fixtures import *
from .util import *
import pygit2


def assertHistoryMatches(rw: 'RepoWidget', locator: NavLocator):
    assert rw.navLocator.similarEnoughTo(locator)
    assert rw.diffView.currentPatch.delta.old_file.path == locator.path
    if locator.context.isDirty():
        assert rw.graphView.currentCommitOid in [None, ""]
        assert rw.filesStack.currentWidget() == rw.stageSplitter
        assert qlvGetSelection(rw.dirtyFiles) == [locator.path]
        assert qlvGetSelection(rw.stagedFiles) == []
    elif locator.context == NavContext.STAGED:
        assert rw.graphView.currentCommitOid in [None, ""]
        assert rw.filesStack.currentWidget() == rw.stageSplitter
        assert qlvGetSelection(rw.stagedFiles) == [locator.path]
        assert qlvGetSelection(rw.dirtyFiles) == []
    else:
        assert rw.graphView.currentCommitOid == locator.commit
        assert rw.filesStack.currentWidget() == rw.committedFilesContainer
        assert qlvGetSelection(rw.committedFiles) == [locator.path]


def testNavigation(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    reposcenario.fileWithStagedAndUnstagedChanges(wd)
    rw = mainWindow.openRepo(wd)

    oid1 = pygit2.Oid(hex="83834a7afdaa1a1260568567f6ad90020389f664")
    oid2 = pygit2.Oid(hex="6e1475206e57110fcef4b92320436c1e9872a322")
    oid3 = pygit2.Oid(hex="bab66b48f836ed950c99134ef666436fb07a09a0")
    oid4 = pygit2.Oid(hex="58be4659bb571194ed4562d04b359d26216f526e")

    # ..........................................# -9 select a1.txt in UNSTAGED
    rw.graphView.selectCommit(oid1)             # -8 select a1.txt in 83834a7
    qlvClickNthRow(rw.committedFiles, 1)        # -7 select a2.txt in 83834a7
    rw.graphView.selectCommit(oid2)             # -6 select b1.txt in 6e14752
    qlvClickNthRow(rw.committedFiles, 1)        # -5 select b2.txt in 6e14752
    rw.graphView.selectUncommittedChanges()     # -4 select a1.txt in UNSTAGED
    qlvClickNthRow(rw.stagedFiles, 0)           # -3 select a1.txt in STAGED
    qlvClickNthRow(rw.dirtyFiles, 0)            # -2 select a1.txt in UNSTAGED again
    rw.graphView.selectCommit(oid3)             # -1 select c1.txt in bab66b4

    history = [
        NavLocator(NavContext.COMMITTED, commit=oid1, path="a/a1.txt"), # -8
        NavLocator(NavContext.COMMITTED, commit=oid1, path="a/a2.txt"), # -7
        NavLocator(NavContext.COMMITTED, commit=oid2, path="b/b1.txt"), # -6
        NavLocator(NavContext.COMMITTED, commit=oid2, path="b/b2.txt"), # -5
        NavLocator(NavContext.UNSTAGED, path="a/a1.txt"),               # -4
        NavLocator(NavContext.STAGED, path="a/a1.txt"),                 # -3
        NavLocator(NavContext.UNSTAGED, path="a/a1.txt"),               # -2
        NavLocator(NavContext.COMMITTED, commit=oid3, path="c/c1.txt"), # -1
    ]

    assertHistoryMatches(rw, history[-1])

    rw.navigateForward()  # can't go further
    assertHistoryMatches(rw, history[-1])

    rw.navigateBack()
    assertHistoryMatches(rw, history[-2])
    rw.navigateForward()
    assertHistoryMatches(rw, history[-1])

    rw.navigateBack()
    assertHistoryMatches(rw, history[-2])

    rw.navigateBack()
    assertHistoryMatches(rw, history[-3])

    rw.navigateBack()
    assertHistoryMatches(rw, history[-4])

    rw.navigateBack()
    assertHistoryMatches(rw, history[-5])

    rw.navigateBack()
    assertHistoryMatches(rw, history[-6])

    rw.navigateBack()
    assertHistoryMatches(rw, history[-7])

    rw.navigateBack()
    assertHistoryMatches(rw, history[-8])

    rw.navigateForward()
    rw.navigateForward()
    rw.navigateForward()
    rw.navigateForward()
    rw.navigateForward()
    assertHistoryMatches(rw, history[-3])

    # now fork from linear history
    rw.graphView.selectCommit(oid4)
    historyFork = NavLocator(NavContext.COMMITTED, commit=oid4, path="master.txt")
    assertHistoryMatches(rw, historyFork)

    # can't go further
    rw.navigateForward()
    assertHistoryMatches(rw, historyFork)

    # go back to -3
    rw.navigateBack()
    assertHistoryMatches(rw, history[-3])

    rw.navigateBack()
    assertHistoryMatches(rw, history[-4])

    rw.navigateForward()
    rw.navigateForward()
    assertHistoryMatches(rw, historyFork)


def testNavigationAfterDiscardingChangeInMiddleOfHistory(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)

    writeFile(F"{wd}/a/a1", "blah blah a1")
    writeFile(F"{wd}/a/a1.txt", "blah blah a1.txt")
    writeFile(F"{wd}/b/b1.txt", "blah blah b1")
    writeFile(F"{wd}/c/c1.txt", "blah blah c1")
    writeFile(F"{wd}/c/c2.txt", "blah blah c2")

    rw = mainWindow.openRepo(wd)

    qlvClickNthRow(rw.dirtyFiles, 0)  # a/a1
    qlvClickNthRow(rw.dirtyFiles, 1)  # a/a1.txt
    qlvClickNthRow(rw.dirtyFiles, 2)  # b/b1.txt
    qlvClickNthRow(rw.dirtyFiles, 3)  # c/c1.txt
    qlvClickNthRow(rw.dirtyFiles, 4)  # c/c2.txt

    assertHistoryMatches(rw, NavLocator(NavContext.UNSTAGED, path="c/c2.txt"))

    rw.navigateBack()
    assertHistoryMatches(rw, NavLocator(NavContext.UNSTAGED, path="c/c1.txt"))
    rw.navigateBack()
    assertHistoryMatches(rw, NavLocator(NavContext.UNSTAGED, path="b/b1.txt"))

    rw.dirtyFiles.discard()  # discard b/b1.txt
    acceptQMessageBox(rw, "really discard changes")

    assertHistoryMatches(rw, NavLocator(NavContext.UNSTAGED, path="c/c1.txt"))

    # can't go further; the FLV's selection has snapped to c1, which has in turn trimmed the history
    rw.navigateForward()
    assertHistoryMatches(rw, NavLocator(NavContext.UNSTAGED, path="c/c1.txt"))

    # navigating back must skip over b1.txt because it's gone
    rw.navigateBack()
    assertHistoryMatches(rw, NavLocator(NavContext.UNSTAGED, path="a/a1.txt"))

    # navigating forward must skip over b1.txt because it's gone
    rw.navigateForward()
    assertHistoryMatches(rw, NavLocator(NavContext.UNSTAGED, path="c/c1.txt"))


def testNavigationAfterDiscardingChangeAtTopOfHistory(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    writeFile(F"{wd}/a/a1", "blah blah a1")
    writeFile(F"{wd}/a/a1.txt", "blah blah a1.txt")
    writeFile(F"{wd}/b/b1.txt", "blah blah b1")
    writeFile(F"{wd}/c/c1.txt", "blah blah c1")
    writeFile(F"{wd}/c/c2.txt", "blah blah c2")
    rw = mainWindow.openRepo(wd)

    qlvClickNthRow(rw.dirtyFiles, 0)
    qlvClickNthRow(rw.dirtyFiles, 1)
    qlvClickNthRow(rw.dirtyFiles, 2)
    qlvClickNthRow(rw.dirtyFiles, 3)
    qlvClickNthRow(rw.dirtyFiles, 4)

    assertHistoryMatches(rw, NavLocator(NavContext.UNSTAGED, path="c/c2.txt"))
    rw.dirtyFiles.discard()
    acceptQMessageBox(rw, "really discard changes")

    assertHistoryMatches(rw, NavLocator(NavContext.UNSTAGED, path="c/c1.txt"))

    # Can't go further
    for i in range(10):
        rw.navigateForward()
        assertHistoryMatches(rw, NavLocator(NavContext.UNSTAGED, path="c/c1.txt"))

    qlvClickNthRow(rw.dirtyFiles, 0)
    assertHistoryMatches(rw, NavLocator(NavContext.UNSTAGED, path="a/a1"))

    rw.navigateBack()
    assertHistoryMatches(rw, NavLocator(NavContext.UNSTAGED, path="c/c1.txt"))

    rw.navigateBack()
    assertHistoryMatches(rw, NavLocator(NavContext.UNSTAGED, path="b/b1.txt"))


def testRestoreLastSelectedFileInContext(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    writeFile(F"{wd}/a/a1", "blah blah a1")
    writeFile(F"{wd}/a/a1.txt", "blah blah a1.txt")
    writeFile(F"{wd}/b/b1.txt", "blah blah b1")
    writeFile(F"{wd}/c/c1.txt", "blah blah c1")
    writeFile(F"{wd}/c/c2.txt", "blah blah c2")
    rw = mainWindow.openRepo(wd)

    oid1 = pygit2.Oid(hex="83834a7afdaa1a1260568567f6ad90020389f664")
    oid2 = pygit2.Oid(hex="6e1475206e57110fcef4b92320436c1e9872a322")

    # Stage c1 and c2
    qlvClickNthRow(rw.dirtyFiles, 3); rw.dirtyFiles.stage()
    qlvClickNthRow(rw.dirtyFiles, 4); rw.dirtyFiles.stage()

    # Select b1.txt in UNSTAGED context
    qlvClickNthRow(rw.dirtyFiles, 2)
    assertHistoryMatches(rw, NavLocator(NavContext.UNSTAGED, path="b/b1.txt"))

    # Select c2.txt in STAGED context
    qlvClickNthRow(rw.stagedFiles, 1)
    assertHistoryMatches(rw, NavLocator(NavContext.STAGED, path="c/c2.txt"))

    # Select a2.txt in COMMITTED context (83834a7)
    rw.graphView.selectCommit(oid1)
    qlvClickNthRow(rw.committedFiles, 1)
    assertHistoryMatches(rw, NavLocator(NavContext.COMMITTED, commit=oid1, path="a/a2.txt"))

    # Select b2.txt in COMMITTED context (6e14752)
    rw.graphView.selectCommit(oid2)
    qlvClickNthRow(rw.committedFiles, 1)
    assertHistoryMatches(rw, NavLocator(NavContext.COMMITTED, commit=oid2, path="b/b2.txt"))

    # Rewind
    rw.navigateBack()  # back to first file in 6e14752
    rw.navigateBack()  # back to a2.txt in 83834a7
    rw.navigateBack()  # back to first file in 83834a7
    rw.navigateBack()  # back to STAGED
    rw.navigateBack()  # back to UNSTAGED

    # Back to UNSTAGED context
    assertHistoryMatches(rw, NavLocator(NavContext.UNSTAGED, path="b/b1.txt"))

    # Advance to STAGED context
    rw.navigateForward()
    assertHistoryMatches(rw, NavLocator(NavContext.STAGED, path="c/c2.txt"))

    # Advance to COMMITTED context (83834a7)
    rw.navigateForward()  # skip automatically selected file in 83834a7
    rw.navigateForward()
    assertHistoryMatches(rw, NavLocator(NavContext.COMMITTED, commit=oid1, path="a/a2.txt"))

    # Advance to COMMITTED context (6e14752)
    rw.navigateForward()  # skip automatically selected file in 6e14752
    rw.navigateForward()
    assertHistoryMatches(rw, NavLocator(NavContext.COMMITTED, commit=oid2, path="b/b2.txt"))
