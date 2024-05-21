import pytest

from gitfourchette.nav import NavLocator
from . import reposcenario
from .util import *
from gitfourchette.porcelain import *


def testConflictDeletedByUs(tempDir, mainWindow):
    wd = unpackRepo(tempDir)

    with RepoContext(wd) as repo:
        # Prepare "their" modification (modify a1.txt and a2.txt)
        writeFile(f"{wd}/a/a1.txt", "they modified")
        writeFile(f"{wd}/a/a2.txt", "they modified")
        repo.index.add_all(["a/a1.txt", "a/a2.txt"])
        oid = repo.create_commit_on_head("they modified 2 files", TEST_SIGNATURE, TEST_SIGNATURE)

        # Switch to no-parent (it has no a1.txt and a2.txt) and merge "their" modification
        assert not repo.any_conflicts
        repo.checkout_local_branch("no-parent")
        repo.cherrypick(oid)
        assert repo.any_conflicts
        assert "a/a1.txt" in repo.index.conflicts
        assert "a/a2.txt" in repo.index.conflicts

    rw = mainWindow.openRepo(wd)

    # Keep our deletion of a1.txt
    assert qlvGetRowData(rw.dirtyFiles) == ["a/a1.txt", "a/a2.txt"]
    assert qlvGetRowData(rw.stagedFiles) == []
    qlvClickNthRow(rw.dirtyFiles, 0)
    assert rw.conflictView.ui.radioDbuOurs.isVisibleTo(rw)
    rw.conflictView.ui.radioDbuOurs.click()
    rw.conflictView.ui.confirmButton.click()

    # Take their a2.txt
    assert qlvGetRowData(rw.dirtyFiles) == ["a/a2.txt"]
    assert qlvGetRowData(rw.stagedFiles) == []
    qlvClickNthRow(rw.dirtyFiles, 0)
    assert rw.conflictView.ui.radioDbuTheirs.isVisibleTo(rw)
    rw.conflictView.ui.radioDbuTheirs.click()
    rw.conflictView.ui.confirmButton.click()

    assert not rw.repo.index.conflicts
    assert not rw.conflictView.isVisibleTo(rw)
    assert rw.repo.status() == {"a/a2.txt": FileStatus.INDEX_NEW}


def testConflictDeletedByThem(tempDir, mainWindow):
    wd = unpackRepo(tempDir)

    with RepoContext(wd) as repo:
        # Prepare "their" modification (delete a1.txt and a2.txt)
        repo.index.remove_all(["a/a1.txt", "a/a2.txt"])
        oid = repo.create_commit_on_head("they deleted 2 files", TEST_SIGNATURE, TEST_SIGNATURE)

        repo.checkout_local_branch("no-parent")

        writeFile(f"{wd}/a/a1.txt", "we modified")
        writeFile(f"{wd}/a/a2.txt", "we modified")
        repo.index.add_all(["a/a1.txt", "a/a2.txt"])
        repo.create_commit_on_head("we touched 2 files", TEST_SIGNATURE, TEST_SIGNATURE)

        assert not repo.any_conflicts
        repo.cherrypick(oid)
        assert repo.any_conflicts
        assert "a/a1.txt" in repo.index.conflicts
        assert "a/a2.txt" in repo.index.conflicts

    rw = mainWindow.openRepo(wd)

    # Keep our a1.txt
    assert qlvGetRowData(rw.dirtyFiles) == ["a/a1.txt", "a/a2.txt"]
    assert qlvGetRowData(rw.stagedFiles) == []
    qlvClickNthRow(rw.dirtyFiles, 0)
    assert rw.conflictView.ui.radioDbtOurs.isVisibleTo(rw)
    rw.conflictView.ui.radioDbtOurs.click()
    rw.conflictView.ui.confirmButton.click()

    # Take their deletion of a2.txt
    assert qlvGetRowData(rw.dirtyFiles) == ["a/a2.txt"]
    assert qlvGetRowData(rw.stagedFiles) == []
    qlvClickNthRow(rw.dirtyFiles, 0)
    assert rw.conflictView.ui.radioDbtTheirs.isVisibleTo(rw)
    rw.conflictView.ui.radioDbtTheirs.click()
    rw.conflictView.ui.confirmButton.click()

    assert not rw.repo.index.conflicts
    assert not rw.conflictView.isVisibleTo(rw)
    assert rw.repo.status() == {"a/a2.txt": FileStatus.INDEX_DELETED}


def testConflictDoesntPreventManipulatingIndexOnOtherFile(tempDir, mainWindow):
    wd = unpackRepo(tempDir)

    with RepoContext(wd) as repo:
        # Prepare "their" modification (modify a1.txt)
        writeFile(f"{wd}/a/a1.txt", "they modified")
        repo.index.add_all(["a/a1.txt"])
        oid = repo.create_commit_on_head("they modified a1.txt", TEST_SIGNATURE, TEST_SIGNATURE)

        # Switch to no-parent (it has no a1.txt) and merge "their" modification to cause a conflict on a1.txt
        assert not repo.any_conflicts
        repo.checkout_local_branch("no-parent")
        repo.cherrypick(oid)
        assert "a/a1.txt" in repo.index.conflicts

    rw = mainWindow.openRepo(wd)

    # Modify some other file with both staged and unstaged changes
    writeFile(f"{wd}/b/b1.txt", "b1\nb1\nstaged change\n")
    rw.refreshRepo()
    assert qlvGetRowData(rw.dirtyFiles) == ["a/a1.txt", "b/b1.txt"]
    assert qlvGetRowData(rw.stagedFiles) == []
    qlvClickNthRow(rw.dirtyFiles, 1)
    QTest.keyPress(rw.dirtyFiles, Qt.Key.Key_Return)
    assert qlvGetRowData(rw.stagedFiles) == ["b/b1.txt"]

    writeFile(f"{wd}/b/b1.txt", "b1\nb1\nunstaged change\nstaged change\n")
    rw.refreshRepo()
    assert qlvGetRowData(rw.dirtyFiles) == ["a/a1.txt", "b/b1.txt"]
    qlvClickNthRow(rw.dirtyFiles, 1)
    QTest.keyPress(rw.dirtyFiles, Qt.Key.Key_Delete)
    acceptQMessageBox(rw, r"really discard changes.+b1\.txt")

    assert readFile(f"{wd}/b/b1.txt").decode() == "b1\nb1\nstaged change\n"


def testMergeTool(tempDir, mainWindow):
    noopMergeToolPath = getTestDataPath("editor-shim.sh")
    mergeToolPath = getTestDataPath("merge-shim.sh")
    scratchPath = f"{tempDir.name}/external editor scratch file.txt"

    wd = unpackRepo(tempDir, "testrepoformerging")
    rw = mainWindow.openRepo(wd)
    node = rw.sidebar.findNodeByRef("refs/heads/branch-conflicts")

    # Initiate merge of branch-conflicts into master
    triggerMenuAction(rw.sidebar.makeNodeMenu(node), "merge into.+master")
    acceptQMessageBox(rw, "branch-conflicts.+into.+master.+may cause conflicts")
    rw.jump(NavLocator.inUnstaged(".gitignore"))
    assert rw.repo.index.conflicts
    assert rw.navLocator.isSimilarEnoughTo(NavLocator.inUnstaged(".gitignore"))
    assert rw.conflictView.isVisible()

    # ------------------------------
    # Try merging with a tool that doesn't touch the output file
    mainWindow.onAcceptPrefsDialog({"externalMerge": f'"{noopMergeToolPath}" "{scratchPath}" $M $L $R $B'})

    assert "editor-shim" in rw.conflictView.ui.radioTool.text()
    rw.conflictView.ui.radioTool.click()
    rw.conflictView.ui.confirmButton.click()

    scratchLines = readFile(scratchPath, timeout=1000, unlink=True).decode("utf-8").strip().splitlines()
    QTest.qWait(100)
    assert "[MERGED]" in scratchLines[0]
    assert "[OURS]" in scratchLines[1]
    assert "[THEIRS]" in scratchLines[2]
    assert "exited without completing" in rw.conflictView.ui.explainer.text().lower()

    # ------------------------------
    # Try merging with a missing command
    mainWindow.onAcceptPrefsDialog({"externalMerge": f'"{noopMergeToolPath}-BOGUSCOMMAND" "{scratchPath}" $M $L $R $B'})
    assert "editor-shim" in rw.conflictView.ui.radioTool.text()
    rw.conflictView.ui.radioTool.click()
    rw.conflictView.ui.confirmButton.click()

    QTest.qWait(100)
    rejectQMessageBox(rw, "not.+installed on your machine")

    # ------------------------------
    # Try merging with a tool that errors out
    writeFile(scratchPath, "oops, file locked!")
    os.chmod(scratchPath, 0o400)

    mainWindow.onAcceptPrefsDialog({"externalMerge": f'"{mergeToolPath}" "${scratchPath}" $M $L $R $B'})
    assert "merge-shim" in rw.conflictView.ui.radioTool.text()
    rw.conflictView.ui.radioTool.click()
    rw.conflictView.ui.confirmButton.click()

    QTest.qWait(100)
    assert "exit code" in rw.conflictView.ui.explainer.text().lower()
    os.unlink(scratchPath)

    # ------------------------------
    # Now try merging with a good tool
    mainWindow.onAcceptPrefsDialog({"externalMerge": f'"{mergeToolPath}" "{scratchPath}" $M $L $R $B'})
    assert "merge-shim" in rw.conflictView.ui.radioTool.text()
    rw.conflictView.ui.radioTool.click()
    rw.conflictView.ui.confirmButton.click()

    scratchText = readFile(scratchPath, timeout=1000, unlink=True).decode("utf-8")
    scratchLines = scratchText.strip().splitlines()
    QTest.qWait(100)

    assert "[MERGED]" in scratchLines[0]
    assert "[OURS]" in scratchLines[1]
    assert "[THEIRS]" in scratchLines[2]
    assert "merge complete!" == readFile(scratchLines[0]).decode("utf-8").strip()

    acceptQMessageBox(rw, "looks like.+resolved")
    assert rw.navLocator.isSimilarEnoughTo(NavLocator.inStaged(".gitignore"))

    assert rw.mergeBanner.isVisible()
    assert "all conflicts fixed" in rw.mergeBanner.label.text().lower()
    assert not rw.repo.index.conflicts


def testMergeToolInBackgroundTab(tempDir, mainWindow):
    mergeToolPath = getTestDataPath("merge-shim.sh")
    scratchPath = f"{tempDir.name}/external editor scratch file.txt"
    mainWindow.onAcceptPrefsDialog({"externalMerge": f'"{mergeToolPath}" "{scratchPath}" $M $L $R $B'})

    otherWd = unpackRepo(tempDir, "TestEmptyRepository")
    wd = unpackRepo(tempDir, "testrepoformerging")
    otherRw = mainWindow.openRepo(otherWd)
    QTest.qWait(1)  # let it settle
    rw = mainWindow.openRepo(wd)
    node = rw.sidebar.findNodeByRef("refs/heads/branch-conflicts")

    # Initiate merge of branch-conflicts into master
    triggerMenuAction(rw.sidebar.makeNodeMenu(node), "merge into.+master")
    acceptQMessageBox(rw, "branch-conflicts.+into.+master.+may cause conflicts")
    rw.jump(NavLocator.inUnstaged(".gitignore"))
    assert rw.repo.index.conflicts
    assert rw.navLocator.isSimilarEnoughTo(NavLocator.inUnstaged(".gitignore"))
    assert rw.conflictView.isVisible()

    assert "merge-shim" in rw.conflictView.ui.radioTool.text()
    rw.conflictView.ui.radioTool.click()
    rw.conflictView.ui.confirmButton.click()
    mainWindow.tabs.setCurrentIndex(0)  # immediately switch to another tab
    assert mainWindow.currentRepoWidget() is otherRw

    scratchText = readFile(scratchPath, timeout=1000, unlink=True).decode("utf-8")
    scratchLines = scratchText.strip().splitlines()
    assert "[MERGED]" in scratchLines[0]
    assert "[OURS]" in scratchLines[1]
    assert "[THEIRS]" in scratchLines[2]
    assert "merge complete!" == readFile(scratchLines[0]).decode("utf-8").strip()
    QTest.qWait(100)

    # Our tab is in the background so it must NOT show a messagebox yet
    with pytest.raises(AssertionError):
        acceptQMessageBox(rw, "looks like.+resolved")

    mainWindow.tabs.setCurrentIndex(1)  # switch BACK to our tab
    QTest.qWait(1)
    acceptQMessageBox(rw, "looks like.+resolved")

    assert rw.navLocator.isSimilarEnoughTo(NavLocator.inStaged(".gitignore"))
    assert rw.mergeBanner.isVisible()
    assert "all conflicts fixed" in rw.mergeBanner.label.text().lower()
    assert not rw.repo.index.conflicts
