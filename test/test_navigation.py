from gitfourchette.nav import NavContext
from . import reposcenario
from .fixtures import *
from .util import *
import pygit2


def testNavigation(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    reposcenario.fileWithStagedAndUnstagedChanges(wd)
    rw = mainWindow.openRepo(wd)

    oid1 = pygit2.Oid(hex="83834a7afdaa1a1260568567f6ad90020389f664")
    oid2 = pygit2.Oid(hex="6e1475206e57110fcef4b92320436c1e9872a322")
    oid3 = pygit2.Oid(hex="bab66b48f836ed950c99134ef666436fb07a09a0")
    oid4 = pygit2.Oid(hex="58be4659bb571194ed4562d04b359d26216f526e")

    rw.graphView.selectCommit(oid1)             # -8
    qlvClickNthRow(rw.committedFiles, 1)        # -7
    rw.graphView.selectCommit(oid2)             # -6
    qlvClickNthRow(rw.committedFiles, 1)        # -5
    rw.graphView.selectUncommittedChanges()     # -4
    qlvClickNthRow(rw.stagedFiles, 0)           # -3
    qlvClickNthRow(rw.dirtyFiles, 0)            # -2
    rw.graphView.selectCommit(oid3)             # -1

    history = [
        (oid1, "a/a1.txt"),                     # -8
        (oid1, "a/a2.txt"),                     # -7
        (oid2, "b/b1.txt"),                     # -6
        (oid2, "b/b2.txt"),                     # -5
        ("UNSTAGED", "a/a1.txt"),               # -4
        ("STAGED", "a/a1.txt"),                 # -3
        ("UNSTAGED", "a/a1.txt"),               # -2
        (oid3, "c/c1.txt"),                     # -1
    ]

    def assertHistoryMatches(t):
        context, selectedFile = t
        if context in ["UNSTAGED", "UNTRACKED"]:
            assert rw.graphView.currentCommitOid in [None, ""]
            assert rw.filesStack.currentWidget() == rw.stageSplitter
            assert qlvGetSelection(rw.dirtyFiles) == [selectedFile]
            assert qlvGetSelection(rw.stagedFiles) == []
        elif context == "STAGED":
            assert rw.graphView.currentCommitOid in [None, ""]
            assert rw.filesStack.currentWidget() == rw.stageSplitter
            assert qlvGetSelection(rw.stagedFiles) == [selectedFile]
            assert qlvGetSelection(rw.dirtyFiles) == []
        else:
            assert rw.graphView.currentCommitOid == context
            assert rw.filesStack.currentWidget() == rw.committedFilesContainer
            assert qlvGetSelection(rw.committedFiles) == [selectedFile]

    assertHistoryMatches(history[-1])

    rw.navigateForward()  # can't go further
    assertHistoryMatches(history[-1])

    rw.navigateBack()
    assertHistoryMatches(history[-2])
    rw.navigateForward()
    assertHistoryMatches(history[-1])

    rw.navigateBack()
    assertHistoryMatches(history[-2])

    rw.navigateBack()
    assertHistoryMatches(history[-3])

    rw.navigateBack()
    assertHistoryMatches(history[-4])

    rw.navigateBack()
    assertHistoryMatches(history[-5])

    rw.navigateBack()
    assertHistoryMatches(history[-6])

    rw.navigateBack()
    assertHistoryMatches(history[-7])

    rw.navigateBack()
    assertHistoryMatches(history[-8])

    rw.navigateForward()
    rw.navigateForward()
    rw.navigateForward()
    rw.navigateForward()
    rw.navigateForward()
    assertHistoryMatches(history[-3])

    # now fork from linear history
    rw.graphView.selectCommit(oid4)
    assertHistoryMatches( (oid4, "master.txt") )

    # can't go further
    rw.navigateForward()
    assertHistoryMatches( (oid4, "master.txt") )

    # go back to -3
    rw.navigateBack()
    assertHistoryMatches(history[-3])

    rw.navigateBack()
    assertHistoryMatches(history[-4])

    rw.navigateForward()
    rw.navigateForward()
    assertHistoryMatches( (oid4, "master.txt") )


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

    assert qlvGetSelection(rw.dirtyFiles) == ["c/c2.txt"]

    rw.navigateBack()
    assert qlvGetSelection(rw.dirtyFiles) == ["c/c1.txt"]
    rw.navigateBack()
    assert qlvGetSelection(rw.dirtyFiles) == ["b/b1.txt"]

    rw.dirtyFiles.discard()  # discard b/b1.txt
    acceptQMessageBox(rw, "really discard changes")

    assert qlvGetSelection(rw.dirtyFiles) == ["c/c1.txt"]

    rw.navigateForward()
    assert qlvGetSelection(rw.dirtyFiles) == ["c/c2.txt"]

    # can't go further
    rw.navigateForward()
    assert qlvGetSelection(rw.dirtyFiles) == ["c/c2.txt"]

    rw.navigateBack()
    assert qlvGetSelection(rw.dirtyFiles) == ["c/c1.txt"]


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

    assert qlvGetSelection(rw.dirtyFiles) == ["c/c2.txt"]
    rw.dirtyFiles.discard()
    acceptQMessageBox(rw, "really discard changes")

    assert qlvGetSelection(rw.dirtyFiles) == ["c/c1.txt"]

    # Can't go further
    for i in range(10):
        rw.navigateForward()
        assert qlvGetSelection(rw.dirtyFiles) == ["c/c1.txt"]

    qlvClickNthRow(rw.dirtyFiles, 0)
    assert qlvGetSelection(rw.dirtyFiles) == ["a/a1"]

    rw.navigateBack()
    assert qlvGetSelection(rw.dirtyFiles) == ["c/c1.txt"]

    rw.navigateBack()
    assert qlvGetSelection(rw.dirtyFiles) == ["b/b1.txt"]


def testRestoreLastSelectedFileInContext(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    writeFile(F"{wd}/a/a1", "blah blah a1")
    writeFile(F"{wd}/a/a1.txt", "blah blah a1.txt")
    writeFile(F"{wd}/b/b1.txt", "blah blah b1")
    writeFile(F"{wd}/c/c1.txt", "blah blah c1")
    writeFile(F"{wd}/c/c2.txt", "blah blah c2")
    rw = mainWindow.openRepo(wd)

    # Stage c1 and c2
    qlvClickNthRow(rw.dirtyFiles, 3); rw.dirtyFiles.stage()
    qlvClickNthRow(rw.dirtyFiles, 4); rw.dirtyFiles.stage()

    # Select b1.txt in UNSTAGED context
    qlvClickNthRow(rw.dirtyFiles, 2)
    assert rw.navLocator.context == NavContext.UNSTAGED
    assert qlvGetSelection(rw.dirtyFiles) == ["b/b1.txt"]

    # Select c2.txt in STAGED context
    qlvClickNthRow(rw.stagedFiles, 1)
    assert rw.navLocator.context == NavContext.STAGED
    assert qlvGetSelection(rw.stagedFiles) == ["c/c2.txt"]

    # Select a2.txt in COMMITTED context (83834a7)
    rw.graphView.selectCommit(pygit2.Oid(hex="83834a7afdaa1a1260568567f6ad90020389f664"))
    qlvClickNthRow(rw.committedFiles, 1)
    assert qlvGetSelection(rw.committedFiles) == ["a/a2.txt"]
    assert rw.navLocator.context == NavContext.COMMITTED

    # Select b2.txt in COMMITTED context (6e14752)
    rw.graphView.selectCommit(pygit2.Oid(hex="6e1475206e57110fcef4b92320436c1e9872a322"))
    qlvClickNthRow(rw.committedFiles, 1)
    assert qlvGetSelection(rw.committedFiles) == ["b/b2.txt"]
    assert rw.navLocator.context == NavContext.COMMITTED

    # Rewind
    rw.navigateBack()  # back to first file in 6e14752
    rw.navigateBack()  # back to a2.txt in 83834a7
    rw.navigateBack()  # back to first file in 83834a7
    rw.navigateBack()  # back to STAGED
    rw.navigateBack()  # back to UNSTAGED

    # Back to UNSTAGED context
    assert rw.navLocator.context == NavContext.UNSTAGED
    assert qlvGetSelection(rw.dirtyFiles) == ["b/b1.txt"]
    assert qlvGetSelection(rw.stagedFiles) == []

    # Advance to STAGED context
    rw.navigateForward()
    assert rw.navLocator.context == NavContext.STAGED
    assert qlvGetSelection(rw.dirtyFiles) == []
    assert qlvGetSelection(rw.stagedFiles) == ["c/c2.txt"]

    # Advance to COMMITTED context (83834a7)
    rw.navigateForward()  # skip automatically selected file in 83834a7
    rw.navigateForward()
    assert rw.navLocator.context == NavContext.COMMITTED
    assert qlvGetSelection(rw.committedFiles) == ["a/a2.txt"]

    # Advance to COMMITTED context (6e14752)
    rw.navigateForward()  # skip automatically selected file in 6e14752
    rw.navigateForward()
    assert rw.navLocator.context == NavContext.COMMITTED
    assert qlvGetSelection(rw.committedFiles) == ["b/b2.txt"]
