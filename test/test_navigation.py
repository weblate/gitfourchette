from . import reposcenario
from .fixtures import *
from .util import *
import pygit2


@withRepo("TestGitRepository")
@withPrep(reposcenario.fileWithStagedAndUnstagedChanges)
def testNavigation(qtbot, workDir, mainWindow, rw):
    oid1 = pygit2.Oid(hex="49322bb17d3acc9146f98c97d078513228bbf3c0")
    oid2 = pygit2.Oid(hex="6e1475206e57110fcef4b92320436c1e9872a322")
    oid3 = pygit2.Oid(hex="bab66b48f836ed950c99134ef666436fb07a09a0")
    oid4 = pygit2.Oid(hex="58be4659bb571194ed4562d04b359d26216f526e")

    rw.selectCommit(oid1)
    qlvClickNthRow(rw.committedFiles, 4)
    rw.selectCommit(oid2)
    qlvClickNthRow(rw.committedFiles, 2)
    rw.graphView.selectUncommittedChanges()
    qlvClickNthRow(rw.stagedFiles, 0)
    qlvClickNthRow(rw.dirtyFiles, 0)
    rw.selectCommit(oid3)

    history = [
        (oid1, "a/a1"),
        (oid1, "c/c2.txt"),
        (oid2, "b/b1.txt"),
        (oid2, "c/c1.txt"),
        ("STAGED", "a/a1.txt"),
        ("UNSTAGED", "a/a1.txt"),
        (oid3, "c/c1.txt"),
    ]

    def assertHistoryMatches(t):
        context, selectedFile = t
        if context == "UNSTAGED":
            assert rw.graphView.currentCommitOid is None
            assert rw.filesStack.currentWidget() == rw.stageSplitter
            assert qlvGetSelection(rw.dirtyFiles) == [selectedFile]
            assert qlvGetSelection(rw.stagedFiles) == []
        elif context == "STAGED":
            assert rw.graphView.currentCommitOid is None
            assert rw.filesStack.currentWidget() == rw.stageSplitter
            assert qlvGetSelection(rw.stagedFiles) == [selectedFile]
            assert qlvGetSelection(rw.dirtyFiles) == []
        else:
            assert rw.graphView.currentCommitOid == context
            assert rw.filesStack.currentWidget() == rw.committedFiles
            assert qlvGetSelection(rw.committedFiles) == [selectedFile]

    assertHistoryMatches(history[-1])

    QTest.mouseClick(mainWindow, Qt.ForwardButton)  # can't go further
    assertHistoryMatches(history[-1])

    QTest.mouseClick(mainWindow, Qt.BackButton)
    QTest.mouseClick(mainWindow, Qt.ForwardButton)
    assertHistoryMatches(history[-1])

    QTest.mouseClick(mainWindow, Qt.BackButton)
    assertHistoryMatches(history[-2])

    QTest.mouseClick(mainWindow, Qt.BackButton)
    assertHistoryMatches(history[-3])

    QTest.mouseClick(mainWindow, Qt.BackButton)
    assertHistoryMatches(history[-4])

    QTest.mouseClick(mainWindow, Qt.BackButton)
    assertHistoryMatches(history[-5])

    QTest.mouseClick(mainWindow, Qt.BackButton)
    assertHistoryMatches(history[-6])

    QTest.mouseClick(mainWindow, Qt.BackButton)
    assertHistoryMatches(history[-7])

    QTest.mouseClick(mainWindow, Qt.ForwardButton)
    QTest.mouseClick(mainWindow, Qt.ForwardButton)
    QTest.mouseClick(mainWindow, Qt.ForwardButton)
    QTest.mouseClick(mainWindow, Qt.ForwardButton)
    assertHistoryMatches(history[-3])

    # now fork from linear history
    rw.selectCommit(oid4)
    assertHistoryMatches( (oid4, "master.txt") )

    # can't go further
    QTest.mouseClick(mainWindow, Qt.ForwardButton)
    assertHistoryMatches( (oid4, "master.txt") )

    # go back to -3
    QTest.mouseClick(mainWindow, Qt.BackButton)
    assertHistoryMatches(history[-3])

    QTest.mouseClick(mainWindow, Qt.BackButton)
    assertHistoryMatches(history[-4])

    QTest.mouseClick(mainWindow, Qt.ForwardButton)
    QTest.mouseClick(mainWindow, Qt.ForwardButton)
    assertHistoryMatches( (oid4, "master.txt") )

