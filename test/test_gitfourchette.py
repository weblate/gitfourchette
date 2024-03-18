from . import reposcenario
from .util import *
from gitfourchette.forms.commitdialog import CommitDialog
from gitfourchette.forms.unloadedrepoplaceholder import UnloadedRepoPlaceholder
from gitfourchette.nav import NavLocator


def testEmptyRepo(tempDir, mainWindow):
    wd = unpackRepo(tempDir, "TestEmptyRepository")
    assert mainWindow.openRepo(wd)
    assert mainWindow.tabs.count() == 1
    mainWindow.closeCurrentTab()  # mustn't crash
    assert mainWindow.tabs.count() == 0


def testChangedFilesShownAtStart(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    touchFile(F"{wd}/SomeNewFile.txt")
    rw = mainWindow.openRepo(wd)

    assert rw.graphView.model().rowCount() > 5
    assert rw.dirtyFiles.isVisibleTo(rw)
    assert rw.stagedFiles.isVisibleTo(rw)
    assert not rw.committedFiles.isVisibleTo(rw)
    assert qlvGetRowData(rw.dirtyFiles) == ["SomeNewFile.txt"]
    assert qlvGetRowData(rw.stagedFiles) == []


def testDisplayAllNestedUntrackedFiles(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    os.mkdir(F"{wd}/N")
    touchFile(F"{wd}/N/tata.txt")
    touchFile(F"{wd}/N/toto.txt")
    touchFile(F"{wd}/N/tutu.txt")
    rw = mainWindow.openRepo(wd)
    assert qlvGetRowData(rw.dirtyFiles) == ["N/tata.txt", "N/toto.txt", "N/tutu.txt"]
    assert qlvGetRowData(rw.stagedFiles) == []


def testParentlessCommitFileList(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)

    commitOid = Oid(hex="42e4e7c5e507e113ebbb7801b16b52cf867b7ce1")
    rw.graphView.selectCommit(commitOid)
    assert qlvGetRowData(rw.committedFiles) == ["c/c1.txt"]


def testSaveOldRevision(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)

    commitOid = Oid(hex="6462e7d8024396b14d7651e2ec11e2bbf07a05c4")

    rw.graphView.selectCommit(commitOid)
    assert qlvGetRowData(rw.committedFiles) == ["c/c2.txt"]
    rw.committedFiles.selectRow(0)
    rw.committedFiles.saveRevisionAs(saveInto=tempDir.name)

    with open(F"{tempDir.name}/c2@6462e7d.txt", "rb") as f:
        contents = f.read()
        assert contents == b"c2\n"


def testSaveOldRevisionOfDeletedFile(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)

    commitOid = Oid(hex="c9ed7bf12c73de26422b7c5a44d74cfce5a8993b")

    rw.graphView.selectCommit(commitOid)
    assert qlvGetRowData(rw.committedFiles) == ["c/c2-2.txt"]
    rw.committedFiles.selectRow(0)

    # c2-2.txt was deleted by the commit.
    # Expect GF to warn us about it.
    rw.committedFiles.saveRevisionAs(saveInto=tempDir.name, beforeCommit=False)
    acceptQMessageBox(rw, r"file.+deleted by.+commit")


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


def testUnloadRepoWhenFolderGoesMissing(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    assert rw.isLoaded

    rw.state.uiPrefs.draftCommitMessage = "some bogus change to prevent prefs to be written"
    rw.state.uiPrefs.write(force=True)
    assert os.path.isfile(f"{wd}/.git/gitfourchette.json")

    os.rename(wd, os.path.normpath(wd) + "-2")

    mainWindow.refreshRepo()
    assert not rw.isLoaded

    urp: UnloadedRepoPlaceholder = rw.placeholderWidget
    assert urp is not None
    assert isinstance(urp, UnloadedRepoPlaceholder)
    assert urp.isVisibleTo(rw)
    assert re.search(r"folder.+missing", urp.ui.label.text(), re.I)

    # Make sure we're not writing the prefs to a ghost directory structure upon exiting
    assert not os.path.isfile(f"{wd}/.git/gitfourchette.json")


def testSkipRenameDetection(tempDir, mainWindow):
    wd = unpackRepo(tempDir)

    with RepoContext(wd, write_index=True) as repo:
        os.rename(f"{wd}/a/a2.txt", f"{wd}/a/a2-renamed.txt")
        repo.index.remove("a/a2.txt")
        repo.index.add("a/a2-renamed.txt")
        for i in range(100):
            writeFile(f"{wd}/bogus{i:03}.txt", f"hello {i}\n")
            repo.index.add(f"bogus{i:03}.txt")
        oid = repo.create_commit_on_head("renamed a2.txt and added a ton of files")

    rw = mainWindow.openRepo(wd)
    assert rw.isLoaded
    assert not rw.diffBanner.isVisibleTo(rw)

    rw.jump(NavLocator.inCommit(oid))
    assert 102 == len(qlvGetRowData(rw.committedFiles))
    assert rw.diffBanner.isVisibleTo(rw)
    assert rw.diffBanner.button.isVisibleTo(rw)
    assert "rename" in rw.diffBanner.label.text().lower()
    assert "detect" in rw.diffBanner.button.text().lower()

    rw.diffBanner.button.click()
    assert 101 == len(qlvGetRowData(rw.committedFiles))
    assert rw.diffBanner.isVisibleTo(rw)
    print(rw.diffBanner.label.text())
    assert re.search(r"1 rename.* detected", rw.diffBanner.label.text(), re.I)
