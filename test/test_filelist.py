import pytest

from .util import *
from . import reposcenario
from gitfourchette.nav import NavLocator, NavContext


def testParentlessCommitFileList(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)

    oid = Oid(hex="42e4e7c5e507e113ebbb7801b16b52cf867b7ce1")
    rw.jump(NavLocator.inCommit(oid))
    assert qlvGetRowData(rw.committedFiles) == ["c/c1.txt"]


def testSaveRevisionAtCommit(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)

    oid = Oid(hex="1203b03dc816ccbb67773f28b3c19318654b0bc8")
    loc = NavLocator.inCommit(oid, "c/c2.txt")
    rw.jump(loc)
    assert loc.isSimilarEnoughTo(rw.navLocator)

    triggerMenuAction(rw.committedFiles.makeContextMenu(), f"save a copy/at 1203b03")
    acceptQFileDialog(rw, "save.+revision as", f"{tempDir.name}/")
    assert b"c2\nc2\n" == readFile(f"{tempDir.name}/c2@1203b03.txt")


def testSaveRevisionBeforeCommit(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)

    oid = Oid(hex="1203b03dc816ccbb67773f28b3c19318654b0bc8")
    loc = NavLocator.inCommit(oid, "c/c2.txt")
    rw.jump(loc)
    assert loc.isSimilarEnoughTo(rw.navLocator)

    triggerMenuAction(rw.committedFiles.makeContextMenu(), f"save a copy/before 1203b03")
    acceptQFileDialog(rw, "save.+revision as", f"{tempDir.name}/")
    assert b"c2\n" == readFile(f"{tempDir.name}/c2@before-1203b03.txt")


def testSaveOldRevisionOfDeletedFile(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)

    commitId = Oid(hex="c9ed7bf12c73de26422b7c5a44d74cfce5a8993b")

    rw.jump(NavLocator.inCommit(commitId))
    assert qlvGetRowData(rw.committedFiles) == ["c/c2-2.txt"]
    rw.committedFiles.selectRow(0)

    # c2-2.txt was deleted by the commit. Expect a warning about this.
    triggerMenuAction(rw.committedFiles.makeContextMenu(), "save a copy/at c9ed7b")
    acceptQMessageBox(rw, r"file.+deleted by.+commit")


@pytest.mark.parametrize("context", [NavContext.UNSTAGED, NavContext.STAGED])
def testRefreshKeepsMultiFileSelection(tempDir, mainWindow, context):
    wd = unpackRepo(tempDir)
    N = 10
    for i in range(N):
        writeFile(f"{wd}/UNSTAGED{i}", f"dirty{i}")
        writeFile(f"{wd}/STAGED{i}", f"staged{i}")
    with RepoContext(wd) as repo:
        repo.index.add_all([f"STAGED{i}" for i in range(N)])
        repo.index.write()

    rw = mainWindow.openRepo(wd)
    fl = rw.fileListByContext(context)
    fl.selectAll()
    rw.refreshRepo()
    assert list(fl.selectedPaths()) == [f"{context.name}{i}" for i in range(N)]


def testSearchFileList(mainWindow, tempDir):
    oid = Oid(hex="83834a7afdaa1a1260568567f6ad90020389f664")

    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)

    rw.jump(NavLocator.inCommit(oid))
    assert rw.committedFiles.isVisibleTo(rw)
    rw.committedFiles.setFocus()
    QTest.keySequence(rw, QKeySequence.StandardKey.Find)

    fileList = rw.committedFiles
    searchBar = fileList.searchBar
    assert searchBar.isVisibleTo(rw)
    searchBar.lineEdit.setText(".txt")
    QTest.qWait(0)
    assert not searchBar.isRed()

    # Send StandardKey instead of "F3" because the bindings are different on macOS
    keyNext = QKeySequence.StandardKey.FindNext
    keyPrev = QKeySequence.StandardKey.FindPrevious

    assert qlvGetSelection(fileList) == ["a/a1.txt"]
    QTest.keySequence(rw, keyNext)
    assert qlvGetSelection(fileList) == ["a/a2.txt"]
    QTest.keySequence(rw, keyNext)
    assert qlvGetSelection(fileList) == ["master.txt"]
    QTest.keySequence(rw, keyNext)
    assert qlvGetSelection(fileList) == ["a/a1.txt"]  # wrap around
    QTest.keySequence(rw, keyPrev)
    assert qlvGetSelection(fileList) == ["master.txt"]

    searchBar.lineEdit.setText("a2")
    QTest.qWait(0)
    assert qlvGetSelection(fileList) == ["a/a2.txt"]

    searchBar.lineEdit.setText("bogus")
    QTest.qWait(0)
    assert searchBar.isRed()

    QTest.keySequence(rw, QKeySequence.StandardKey.FindNext)
    acceptQMessageBox(rw, "not found")

    QTest.keySequence(rw, QKeySequence.StandardKey.FindPrevious)
    acceptQMessageBox(rw, "not found")

    QTest.keySequence(searchBar, "Escape")
    QTest.qWait(0)
    assert not searchBar.isVisibleTo(rw)


def testSearchEmptyFileList(mainWindow, tempDir):
    wd = unpackRepo(tempDir)
    with RepoContext(wd) as repo:
        oid = repo.create_commit_on_head("EMPTY COMMIT")
    rw = mainWindow.openRepo(wd)

    rw.jump(NavLocator.inCommit(oid))
    assert rw.committedFiles.isVisibleTo(rw)
    assert not qlvGetRowData(rw.committedFiles)
    rw.committedFiles.setFocus()
    QTest.keySequence(rw, QKeySequence.StandardKey.Find)

    fileList = rw.committedFiles
    searchBar = fileList.searchBar
    assert searchBar.isVisibleTo(rw)
    searchBar.lineEdit.setText("blah.txt")
    QTest.qWait(0)
    assert searchBar.isRed()

    QTest.keySequence(rw, QKeySequence.StandardKey.FindNext)
    acceptQMessageBox(rw, "not found")

    QTest.keySequence(rw, QKeySequence.StandardKey.FindPrevious)
    acceptQMessageBox(rw, "not found")


def testEditFileInExternalEditor(mainWindow, tempDir):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    rw.jump(NavLocator.inCommit(Oid(hex="49322bb17d3acc9146f98c97d078513228bbf3c0"), "a/a1"))

    editorPath = getTestDataPath("editor-shim.sh")
    scratchPath = f"{tempDir.name}/external editor scratch file.txt"

    # First, set the editor to an incorrect command to go through the "locate" code path
    mainWindow.onAcceptPrefsDialog({"externalEditor": f'"{editorPath}-BOGUSCOMMAND" "{scratchPath}"'})
    triggerMenuAction(rw.committedFiles.makeContextMenu(), "edit in editor-shim/current version")
    QTest.qWait(100 if not MACOS else 500)
    qmb = findQMessageBox(mainWindow, "n.t start text editor")
    qmb.button(QMessageBox.StandardButton.Open).click()  # click "locate" button
    # Set correct command; this must retain the arguments from the incorrect command
    acceptQFileDialog(mainWindow, "locate.+editor-shim", editorPath)

    # Now open the file in our shim
    # HEAD revision
    triggerMenuAction(rw.committedFiles.makeContextMenu(), "edit in editor-shim/current")
    assert b"a/a1" in readFile(scratchPath, timeout=1000, unlink=True)

    # New revision
    triggerMenuAction(rw.committedFiles.makeContextMenu(), "edit in editor-shim/before 49322bb")
    acceptQMessageBox(mainWindow, "file did.?n.t exist")

    # Old revision
    triggerMenuAction(rw.committedFiles.makeContextMenu(), "edit in editor-shim/at 49322bb")
    assert b"a1@49322bb" in readFile(scratchPath, timeout=1000, unlink=True)


def testEditFileInExternalDiffTool(mainWindow, tempDir):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    rw.jump(NavLocator.inCommit(Oid(hex="7f822839a2fe9760f386cbbbcb3f92c5fe81def7"), "b/b2.txt"))

    editorPath = getTestDataPath("editor-shim.sh")
    scratchPath = f"{tempDir.name}/external editor scratch file.txt"

    # First, set the diff tool to an empty command to go through the "set up" code path
    mainWindow.onAcceptPrefsDialog({"externalDiff": ""})
    triggerMenuAction(rw.committedFiles.makeContextMenu(), "compare in.+diff tool")
    acceptQMessageBox(mainWindow, "diff tool.+n.t set up")
    findQDialog(mainWindow, "preferences").reject()

    mainWindow.onAcceptPrefsDialog({"externalDiff": f'"{editorPath}" "{scratchPath}" $L $R'})
    triggerMenuAction(rw.committedFiles.makeContextMenu(), "compare in editor-shim")
    scratchText = readFile(scratchPath, 1000, unlink=True).decode("utf-8")
    assert "[OLD]b2.txt" in scratchText
    assert "[NEW]b2.txt" in scratchText


def testFileListToolTip(mainWindow, tempDir):
    wd = unpackRepo(tempDir)
    reposcenario.fileWithStagedAndUnstagedChanges(wd)
    writeFile(f"{wd}/newexe", "okay\n")
    os.chmod(f"{wd}/newexe", 0o777)
    rw = mainWindow.openRepo(wd)

    rw.jump(NavLocator.inUnstaged("a/a1.txt"))
    tip = rw.dirtyFiles.currentIndex().data(Qt.ItemDataRole.ToolTipRole)
    assert all(re.search(p, tip, re.I) for p in ("a/a1.txt", "modified"))

    # look at staged counterpart of current index
    tip = rw.stagedFiles.model().index(0, 0).data(Qt.ItemDataRole.ToolTipRole)
    assert all(re.search(p, tip, re.I) for p in ("a/a1.txt", "modified", "also.+staged"))

    rw.jump(NavLocator.inUnstaged("newexe"))
    tip = rw.dirtyFiles.currentIndex().data(Qt.ItemDataRole.ToolTipRole)
    assert all(re.search(p, tip, re.I) for p in ("untracked", "executable"))

    rw.jump(NavLocator.inCommit(Oid(hex="ce112d052bcf42442aa8563f1e2b7a8aabbf4d17"), "c/c2-2.txt"))
    tip = rw.committedFiles.currentIndex().data(Qt.ItemDataRole.ToolTipRole)
    assert all(re.search(p, tip, re.I) for p in ("c/c2.txt", "c/c2-2.txt", "renamed", "similarity"))
