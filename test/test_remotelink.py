import pytest

from gitfourchette.forms.clonedialog import CloneDialog
from gitfourchette.forms.remotedialog import RemoteDialog
from gitfourchette.nav import NavContext
from .util import *

hasNetwork = os.environ.get("TESTNET", "0").lower() not in ["0", ""]
requiresNetwork = pytest.mark.skipif(not hasNetwork, reason="Requires network - rerun with TESTNET=1 environment variable")


@requiresNetwork
def testHttpsCloneRepo(tempDir, mainWindow, taskThread, qtbot):
    triggerMenuAction(mainWindow.menuBar(), "file/clone")
    cloneDialog: CloneDialog = findQDialog(mainWindow, "clone")
    cloneDialog.ui.urlEdit.setEditText("https://github.com/libgit2/TestGitRepository")
    cloneDialog.ui.pathEdit.setText(tempDir.name + "/cloned")
    cloneDialog.cloneButton.click()
    qtbot.waitSignal(cloneDialog.finished).wait()

    rw = mainWindow.currentRepoWidget()
    qtbot.waitSignal(rw.repoTaskRunner.ready).wait()
    assert "master" in rw.repo.branches.local
    assert "origin/master" in rw.repo.branches.remote
    assert "origin/no-parent" in rw.repo.branches.remote


@requiresNetwork
def testSshCloneRepo(tempDir, mainWindow, taskThread, qtbot):
    triggerMenuAction(mainWindow.menuBar(), "file/clone")
    cloneDialog: CloneDialog = findQDialog(mainWindow, "clone")
    cloneDialog.ui.urlEdit.setEditText("https://github.com/libgit2/TestGitRepository")
    cloneDialog.ui.pathEdit.setText(tempDir.name + "/cloned")

    # Set SSH URL via protocol swap button
    protocolButton = cloneDialog.ui.protocolButton
    assert protocolButton.isVisible()
    assert protocolButton.text() == "https"
    protocolButton.menu().actions()[0].trigger()
    assert protocolButton.text() == "ssh"
    assert cloneDialog.ui.urlEdit.lineEdit().text() == "git@github.com:libgit2/TestGitRepository"

    cloneDialog.ui.keyFilePicker.setPath(getTestDataPath("keys/pygit2_empty.pub"))
    cloneDialog.cloneButton.click()

    passphraseDialog = waitForQDialog(mainWindow, "passphrase")
    passphraseDialog.findChild(QLineEdit).setText("empty")
    passphraseDialog.accept()
    qtbot.waitSignal(cloneDialog.finished).wait()

    rw = mainWindow.currentRepoWidget()
    qtbot.waitSignal(rw.repoTaskRunner.ready).wait()
    assert "master" in rw.repo.branches.local
    assert "origin/master" in rw.repo.branches.remote
    assert "origin/no-parent" in rw.repo.branches.remote


@requiresNetwork
def testHttpsShallowClone(tempDir, mainWindow, taskThread, qtbot):
    triggerMenuAction(mainWindow.menuBar(), "file/clone")
    cloneDialog: CloneDialog = findQDialog(mainWindow, "clone")
    cloneDialog.ui.urlEdit.setEditText("https://github.com/libgit2/TestGitRepository")
    cloneDialog.ui.pathEdit.setText(tempDir.name + "/cloned")
    cloneDialog.ui.shallowCloneCheckBox.setChecked(True)
    cloneDialog.cloneButton.click()
    qtbot.waitSignal(cloneDialog.finished).wait()

    rw = mainWindow.currentRepoWidget()
    qtbot.waitSignal(rw.repoTaskRunner.ready).wait()
    assert "master" in rw.repo.branches.local
    assert "origin/master" in rw.repo.branches.remote
    assert "origin/no-parent" in rw.repo.branches.remote

    # 5 rows: Uncommitted changes; 1 lone commit for each of the 3 branches; Shallow clone row
    assert rw.graphView.clModel.rowCount() == 5

    qlvClickNthRow(rw.graphView, 4)
    assert rw.navLocator.context == NavContext.SPECIAL
    assert rw.specialDiffView.isVisible()
    assert "shallow" in rw.specialDiffView.toPlainText().lower()


@requiresNetwork
def testHttpsAddRemoteAndFetch(tempDir, mainWindow, taskThread, qtbot):
    wd = unpackRepo(tempDir)
    with RepoContext(wd) as repo:
        repo.remotes.delete("origin")
    rw = mainWindow.openRepo(wd)
    qtbot.waitSignal(rw.repoTaskRunner.ready).wait()
    assert "origin/master" not in rw.repo.branches.remote

    triggerMenuAction(mainWindow.menuBar(), "repo/add remote")
    remoteDialog: RemoteDialog = findQDialog(rw, "add remote")
    remoteDialog.ui.urlEdit.setText("https://github.com/libgit2/TestGitRepository")
    remoteDialog.ui.nameEdit.setText("origin")
    remoteDialog.accept()

    qtbot.waitSignal(rw.repoTaskRunner.ready).wait()
    assert "origin/master" in rw.repo.branches.remote


@requiresNetwork
def testSshAddRemoteAndFetch(tempDir, mainWindow, taskThread, qtbot):
    wd = tempDir.name + "/emptyrepo"
    pygit2.init_repository(wd)
    rw = mainWindow.openRepo(wd)
    qtbot.waitSignal(rw.repoTaskRunner.ready).wait()

    triggerMenuAction(mainWindow.menuBar(), "repo/add remote")
    remoteDialog: RemoteDialog = findQDialog(rw, "add remote")
    remoteDialog.ui.urlEdit.setText("ssh://git@github.com/pygit2/empty")
    remoteDialog.ui.nameEdit.setText("origin")
    remoteDialog.ui.keyFilePicker.setPath(getTestDataPath("keys/pygit2_empty.pub"))
    remoteDialog.accept()

    passphraseDialog = waitForQDialog(mainWindow, "passphrase")
    passphraseDialog.findChild(QLineEdit).setText("empty")
    passphraseDialog.accept()

    qtbot.waitSignal(rw.repoTaskRunner.ready).wait()
    assert "origin/master" in rw.repo.branches.remote
