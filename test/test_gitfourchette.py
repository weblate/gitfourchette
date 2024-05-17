import os.path

import pytest

from .util import *
from gitfourchette.forms.commitdialog import CommitDialog
from gitfourchette.forms.prefsdialog import PrefsDialog
from gitfourchette.forms.unloadedrepoplaceholder import UnloadedRepoPlaceholder
from gitfourchette.graphview.commitlogmodel import SpecialRow
from gitfourchette.nav import NavLocator, NavContext
from gitfourchette.sidebar.sidebarmodel import SidebarModel, SidebarNode, EItem


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

    oid = Oid(hex="42e4e7c5e507e113ebbb7801b16b52cf867b7ce1")
    rw.jump(NavLocator.inCommit(oid))
    assert qlvGetRowData(rw.committedFiles) == ["c/c1.txt"]


def testSaveOldRevision(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)

    oid = Oid(hex="6462e7d8024396b14d7651e2ec11e2bbf07a05c4")
    loc = NavLocator.inCommit(oid, "c/c2.txt")
    rw.jump(NavLocator.inCommit(oid, "c/c2.txt"))
    assert loc.isSimilarEnoughTo(rw.navLocator)
    rw.committedFiles.saveRevisionAs(saveInto=tempDir.name)

    with open(F"{tempDir.name}/c2@6462e7d.txt", "rb") as f:
        contents = f.read()
        assert contents == b"c2\n"


def testSaveOldRevisionOfDeletedFile(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)

    commitOid = Oid(hex="c9ed7bf12c73de26422b7c5a44d74cfce5a8993b")

    rw.jump(NavLocator.inCommit(commitOid))
    assert qlvGetRowData(rw.committedFiles) == ["c/c2-2.txt"]
    rw.committedFiles.selectRow(0)

    # c2-2.txt was deleted by the commit.
    # Expect GF to warn us about it.
    rw.committedFiles.saveRevisionAs(saveInto=tempDir.name, beforeCommit=False)
    acceptQMessageBox(rw, r"file.+deleted by.+commit")


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

    rw.diffBanner.dismissButton.click()
    assert not rw.diffBanner.isVisibleTo(rw)


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


def testPrefsDialog(tempDir, mainWindow):
    # Open a repo so that refreshPrefs functions are exercized in coverage
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)

    def openPrefs() -> PrefsDialog:
        triggerMenuAction(mainWindow.menuBar(), "file/preferences")
        return findQDialog(mainWindow, "preferences")

    # Open prefs, navigate to some tab and reject
    dlg = openPrefs()
    assert dlg.tabs.currentIndex() == 0
    dlg.tabs.setCurrentIndex(2)
    dlg.reject()

    # Open prefs again and check that the tab was restored
    dlg = openPrefs()
    assert dlg.tabs.currentIndex() == 2
    dlg.reject()

    # Change statusbar setting, and cancel
    assert mainWindow.statusBar().isVisible()
    dlg = openPrefs()
    checkBox: QCheckBox = dlg.findChild(QCheckBox, "prefctl_showStatusBar")
    assert checkBox.isChecked()
    checkBox.setChecked(False)
    dlg.reject()
    assert mainWindow.statusBar().isVisible()

    # Change statusbar setting, and accept
    dlg = openPrefs()
    checkBox: QCheckBox = dlg.findChild(QCheckBox, "prefctl_showStatusBar")
    assert checkBox.isChecked()
    checkBox.setChecked(False)
    dlg.accept()
    assert not mainWindow.statusBar().isVisible()

    # Play with QComboBoxWithPreview (for coverage)
    dlg = mainWindow.openPrefsDialog("shortTimeFormat")
    comboBox: QComboBox = dlg.findChild(QWidget, "prefctl_shortTimeFormat").findChild(QComboBox)
    comboBox.setFocus()
    QTest.keyClick(comboBox, Qt.Key.Key_Down, Qt.KeyboardModifier.AltModifier)
    QTest.qWait(0)
    QTest.keyClick(comboBox, Qt.Key.Key_Down)
    QTest.qWait(0)
    QTest.keyClick(comboBox, Qt.Key.Key_Down, Qt.KeyboardModifier.AltModifier)
    QTest.qWait(0)  # trigger ItemDelegate.paint
    comboBox.setFocus()
    QTest.keyClicks(comboBox, "MMMM")  # trigger activation of out-of-bounds index
    QTest.keyClick(comboBox, Qt.Key.Key_Enter)
    dlg.reject()


def testNewRepo(tempDir, mainWindow):
    triggerMenuAction(mainWindow.menuBar(), "file/new repo")

    path = os.path.realpath(tempDir.name + "/valoche3000")
    os.makedirs(path)

    dlg: QFileDialog = findQDialog(mainWindow, "new repo")
    assert isinstance(dlg, QFileDialog)
    dlg.setDirectory(path)
    dlg.accept()

    rw = mainWindow.currentRepoWidget()
    assert path == os.path.normpath(rw.repo.workdir)

    assert rw.uiReady
    assert rw.navLocator.context.isWorkdir()

    assert not list(rw.sidebar.findNodesByKind(EItem.LocalBranch))
    unbornNode = next(rw.sidebar.findNodesByKind(EItem.UnbornHead))
    unbornNodeIndex = unbornNode.createIndex(rw.sidebar.sidebarModel)
    assert re.search(r"branch.+will be created", unbornNodeIndex.data(Qt.ItemDataRole.ToolTipRole), re.I)
    # TODO: test that we honor "init.defaultBranch"...without touching user's git config

    rw.commitButton.click()
    acceptQMessageBox(rw, "empty commit")
    commitDialog: CommitDialog = findQDialog(rw, "commit")
    commitDialog.ui.summaryEditor.setText("initial commit")
    commitDialog.accept()

    assert not list(rw.sidebar.findNodesByKind(EItem.UnbornHead))
    branchNode = next(rw.sidebar.findNodesByKind(EItem.LocalBranch))
    branchNodeIndex = branchNode.createIndex(rw.sidebar.sidebarModel)
    assert re.search(r"checked.out", branchNodeIndex.data(Qt.ItemDataRole.ToolTipRole), re.I)


def testNewRepoFromExistingSources(tempDir, mainWindow):
    triggerMenuAction(mainWindow.menuBar(), "file/new repo")

    path = os.path.realpath(tempDir.name + "/valoche3000")
    os.makedirs(path)
    writeFile(f"{path}/existing.txt", "file was here before repo inited\n")

    dlg: QFileDialog = findQDialog(mainWindow, "new repo")
    assert isinstance(dlg, QFileDialog)
    dlg.setDirectory(path)
    dlg.accept()

    acceptQMessageBox(mainWindow, r"are you sure.+valoche3000.+isn.t empty")

    rw = mainWindow.currentRepoWidget()
    rw.jump(NavLocator.inUnstaged("existing.txt"))
    assert "file was here before repo inited" in rw.diffView.toPlainText()


def testNewRepoAtExistingRepo(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    triggerMenuAction(mainWindow.menuBar(), "file/new repo")

    dlg: QFileDialog = findQDialog(mainWindow, "new repo")
    assert isinstance(dlg, QFileDialog)
    dlg.setDirectory(wd)
    dlg.accept()

    qmb = findQMessageBox(mainWindow, "already exists")
    qmb.accept()
    assert wd == mainWindow.currentRepoWidget().repo.workdir


def testNewNestedRepo(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    path = wd + "/valoche3000"
    os.makedirs(path)

    triggerMenuAction(mainWindow.menuBar(), "file/new repo")

    dlg: QFileDialog = findQDialog(mainWindow, "new repo")
    assert isinstance(dlg, QFileDialog)
    dlg.setDirectory(path)
    dlg.accept()

    qmb = findQMessageBox(mainWindow, "TestGitRepository.+parent (dir|folder).+sub(dir|folder)")
    qmb.accept()


@pytest.mark.parametrize("method", ["specialdiff", "graphcm"])
def testTruncatedHistory(mainWindow, tempDir, method):
    bottomCommit = Oid(hex="42e4e7c5e507e113ebbb7801b16b52cf867b7ce1")

    mainWindow.onAcceptPrefsDialog({"maxCommits": 5})
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)
    QTest.qWait(1)
    assert 7 == rw.graphView.clFilter.rowCount()

    # Search bar shouldn't be able to reach bottom commit
    triggerMenuAction(mainWindow.menuBar(), "edit/find")
    QTest.qWait(0)
    assert rw.graphView.searchBar.lineEdit.hasFocus()
    QTest.keyClicks(rw.graphView.searchBar.lineEdit, "first c/c1, no parent")
    QTest.qWait(0)
    assert rw.graphView.searchBar.isRed()
    QTest.keyPress(rw.graphView.searchBar.lineEdit, Qt.Key.Key_Return)
    QTest.qWait(0)
    acceptQMessageBox(rw, "not found.+truncated")
    rw.graphView.searchBar.ui.closeButton.click()

    # Bottom commit contents must be able to be displayed
    rw.jump(NavLocator.inCommit(bottomCommit))
    assert rw.navLocator.commit == bottomCommit
    assert rw.diffBanner.isVisibleTo(rw)
    assert re.search("commit.+n.t shown in the graph", rw.diffBanner.label.text(), re.I)
    assert not rw.graphView.selectedIndexes()

    # Jump to truncated history row
    loc = NavLocator(NavContext.SPECIAL, path=str(SpecialRow.TruncatedHistory))
    rw.jump(loc)
    assert loc.isSimilarEnoughTo(rw.navLocator)
    assert rw.graphView.currentRowKind == SpecialRow.TruncatedHistory
    assert rw.graphView.selectedIndexes()

    assert rw.specialDiffView.isVisibleTo(rw)
    assert "truncated" in rw.specialDiffView.toPlainText().lower()

    # Click "change threshold"
    if method == "specialdiff":
        qteClickLink(rw.specialDiffView, "change.+threshold")
    elif method == "graphcm":
        triggerMenuAction(rw.graphView.makeContextMenu(), "change.+threshold")
    prefsDialog = findQDialog(mainWindow, "preferences")
    QTest.qWait(0)
    assert prefsDialog.findChild(QWidget, "prefctl_maxCommits").hasFocus()
    prefsDialog.reject()

    # Load full commit history
    if method == "specialdiff":
        qteClickLink(rw.specialDiffView, "load full")
    elif method == "graphcm":
        triggerMenuAction(rw.graphView.makeContextMenu(), "load full")
    assert 7 < rw.graphView.clFilter.rowCount()

    # Truncated history row must be gone
    with pytest.raises(ValueError):
        rw.jump(loc)
    rejectQMessageBox(mainWindow, "navigate in repo")  # dismiss error message

    # Bottom commit should work now
    rw.jump(NavLocator.inCommit(bottomCommit))
    assert rw.navLocator.commit == bottomCommit
    assert rw.graphView.selectedIndexes()
    assert not rw.diffBanner.isVisibleTo(rw)


def testRepoNickname(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)

    assert "TestGitRepository" in mainWindow.windowTitle()
    assert "TestGitRepository" in mainWindow.tabs.tabs.tabText(mainWindow.tabs.currentIndex())
    assert findMenuAction(mainWindow.menuBar(), "file/recent/TestGitRepository")

    # Rename to "coolrepo"
    triggerMenuAction(mainWindow.menuBar(), "repo/rename repo")
    dlg = findQDialog(rw, "edit.+name")
    qle: QLineEdit = dlg.findChild(QLineEdit)
    assert qle.text() == "TestGitRepository"
    qle.setText("coolrepo")
    dlg.accept()

    assert "TestGitRepository" not in mainWindow.windowTitle()
    assert "coolrepo" in mainWindow.windowTitle()
    assert "coolrepo" in mainWindow.tabs.tabs.tabText(mainWindow.tabs.currentIndex())
    recentAction = findMenuAction(mainWindow.menuBar(), "file/recent/coolrepo")
    assert recentAction
    assert recentAction is findMenuAction(mainWindow.menuBar(), "file/recent/TestGitRepository")

    # Reset to default name
    triggerMenuAction(mainWindow.menuBar(), "repo/rename repo")
    dlg = findQDialog(rw, "edit.+name")
    qle: QLineEdit = dlg.findChild(QLineEdit)
    assert qle.text() == "coolrepo"
    buttonBox: QDialogButtonBox = dlg.findChild(QDialogButtonBox)
    restoreButton = buttonBox.button(QDialogButtonBox.StandardButton.RestoreDefaults)
    restoreButton.click()
    assert "TestGitRepository" in mainWindow.windowTitle()


def testTabOverflow(tempDir, mainWindow):
    mainWindow.resize(640, 480)  # make sure it's narrow enough for overflow

    for i in range(10):
        wd = unpackRepo(tempDir, renameTo=f"RepoCopy{i:04}")
        rw = mainWindow.openRepo(wd)
        QTest.qWait(1)

        if i <= 2:  # assume no overflow when there are few repos
            assert not mainWindow.tabs.overflowGradient.isVisibleTo(mainWindow)
            assert not mainWindow.tabs.overflowButton.isVisibleTo(mainWindow)

    assert mainWindow.tabs.overflowGradient.isVisibleTo(mainWindow)
    assert mainWindow.tabs.overflowButton.isVisibleTo(mainWindow)


@pytest.mark.skipif(MACOS, reason="this feature is disabled on macOS")
def testAutoHideMenuBar(mainWindow):
    menuBar: QMenuBar = mainWindow.menuBar()
    assert menuBar.isVisible()
    assert menuBar.height() != 0

    # Hide menu bar
    mainWindow.onAcceptPrefsDialog({"showMenuBar": False})
    acceptQMessageBox(mainWindow, "menu bar.+hidden")
    assert menuBar.height() == 0

    QTest.keyClick(mainWindow, Qt.Key.Key_Alt)
    QTest.qWait(0)
    assert menuBar.height() != 0

    QTest.keyClick(mainWindow, Qt.Key.Key_Alt)
    QTest.qWait(0)
    assert menuBar.height() == 0

    QTest.keyPress(menuBar, Qt.Key.Key_F, Qt.KeyboardModifier.AltModifier)
    QTest.qWait(0)
    fileMenu: QMenu = menuBar.findChild(QMenu, "MWFileMenu")
    assert menuBar.height() != 0
    assert fileMenu.isVisibleTo(menuBar)
    QTest.keyRelease(fileMenu, Qt.Key.Key_F, Qt.KeyboardModifier.AltModifier)
    QTest.qWait(0)
    assert menuBar.height() != 0

    QTest.keyClick(fileMenu, Qt.Key.Key_Escape)
    QTest.qWait(0)
    assert not fileMenu.isVisible()
    assert menuBar.height() == 0

    # Restore menu bar
    mainWindow.onAcceptPrefsDialog({"showMenuBar": True})
    QTest.qWait(0)
    assert menuBar.height() != 0


def testAboutDialog(mainWindow):
    triggerMenuAction(mainWindow.menuBar(), "help/about")
    dlg = findQDialog(mainWindow, "about")
    dlg.accept()
