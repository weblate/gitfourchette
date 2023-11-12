from . import reposcenario
from .fixtures import *
from .util import *
from gitfourchette.porcelain import *


def testConflictDeletedByUs(qtbot, tempDir, mainWindow):
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
    qlvClickNthRow(rw.dirtyFiles, 0)
    assert rw.conflictView.ui.radioDbuOurs.isVisibleTo(rw)
    rw.conflictView.ui.radioDbuOurs.click()
    rw.conflictView.ui.confirmButton.click()

    # Take their a2.txt
    assert qlvGetRowData(rw.dirtyFiles) == ["a/a2.txt"]
    qlvClickNthRow(rw.dirtyFiles, 0)
    assert rw.conflictView.ui.radioDbuTheirs.isVisibleTo(rw)
    rw.conflictView.ui.radioDbuTheirs.click()
    rw.conflictView.ui.confirmButton.click()

    assert not rw.repo.index.conflicts
    assert not rw.conflictView.isVisibleTo(rw)
    assert rw.repo.status() == {"a/a2.txt": GIT_STATUS_INDEX_NEW}


def testConflictDeletedByThem(qtbot, tempDir, mainWindow):
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
    qlvClickNthRow(rw.dirtyFiles, 0)
    assert rw.conflictView.ui.radioDbtOurs.isVisibleTo(rw)
    rw.conflictView.ui.radioDbtOurs.click()
    rw.conflictView.ui.confirmButton.click()

    # Take their deletion of a2.txt
    assert qlvGetRowData(rw.dirtyFiles) == ["a/a2.txt"]
    qlvClickNthRow(rw.dirtyFiles, 0)
    assert rw.conflictView.ui.radioDbtTheirs.isVisibleTo(rw)
    rw.conflictView.ui.radioDbtTheirs.click()
    rw.conflictView.ui.confirmButton.click()

    assert not rw.repo.index.conflicts
    assert not rw.conflictView.isVisibleTo(rw)
    assert rw.repo.status() == {"a/a2.txt": GIT_STATUS_INDEX_DELETED}
