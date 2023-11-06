from . import reposcenario
from .fixtures import *
from .util import *
from gitfourchette import porcelain
import pygit2


def testConflictDeletedByUs(qtbot, tempDir, mainWindow):
    wd = unpackRepo(tempDir)

    with RepositoryContext(wd) as repo:
        writeFile(f"{wd}/a/a1.txt", "we'll delete this")
        writeFile(f"{wd}/a/a2.txt", "we'll keep this")
        repo.index.add_all(["a/a1.txt", "a/a2.txt"])

        sig = pygit2.Signature("toto", "toto@example.com", 0, 0)
        oid = porcelain.createCommit(repo, "two modified files", overrideAuthor=sig, overrideCommitter=sig)

        assert not repo.index.conflicts
        porcelain.checkoutLocalBranch(repo, "no-parent")
        porcelain.cherrypick(repo, oid)
        assert repo.index.conflicts
        assert "a/a1.txt" in repo.index.conflicts
        assert "a/a2.txt" in repo.index.conflicts

    rw = mainWindow.openRepo(wd)

    assert qlvGetRowData(rw.dirtyFiles) == ["a/a1.txt", "a/a2.txt"]
    qlvClickNthRow(rw.dirtyFiles, 0)
    assert rw.conflictView.ui.deletedByUsDelete.isVisibleTo(rw)
    rw.conflictView.ui.deletedByUsDelete.click()

    assert qlvGetRowData(rw.dirtyFiles) == ["a/a2.txt"]
    qlvClickNthRow(rw.dirtyFiles, 0)
    assert rw.conflictView.ui.deletedByUsAdd.isVisibleTo(rw)
    rw.conflictView.ui.deletedByUsAdd.click()

    assert not rw.repo.index.conflicts
    assert not rw.conflictView.isVisibleTo(rw)
    assert rw.repo.status() == {"a/a2.txt": pygit2.GIT_STATUS_WT_NEW}
