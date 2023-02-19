"""
Remote access tasks.
"""

from gitfourchette import porcelain
from gitfourchette.qt import *
from gitfourchette.tasks.repotask import RepoTask, TaskAffectsWhat, AbortIfDialogRejected
from gitfourchette.trash import Trash
from gitfourchette import util
from gitfourchette.widgets.remotedialog import RemoteDialog
from gitfourchette.widgets.brandeddialog import showTextInputDialog
from gitfourchette.widgets.remotelinkprogressdialog import RemoteLinkProgressDialog
from html import escape
import os
import pygit2


class _BaseNetTask(RepoTask):
    rlpd: RemoteLinkProgressDialog | None

    def __init__(self, rw):
        super().__init__(rw)
        self.rlpd = None

    def refreshWhat(self) -> TaskAffectsWhat:
        return TaskAffectsWhat.REMOTES

    def showRemoteLinkDialog(self):
        assert not self.rlpd
        assert util.onAppThread()
        self.rlpd = RemoteLinkProgressDialog(self.rw)

    def preExecuteUiFlow(self):
        """ If you override this, make sure to call showRemoteLinkDialog! """
        self.showRemoteLinkDialog()

    def postExecute(self, success: bool):
        if self.rlpd:
            self.rlpd.close()
            self.rlpd.deleteLater()
            self.rlpd = None

    @property
    def remoteLink(self):
        return self.rlpd.remoteLink


class DeleteRemoteBranch(_BaseNetTask):
    def __init__(self, rw, remoteBranchName: str):
        super().__init__(rw)
        self.remoteBranchName = remoteBranchName
        assert not remoteBranchName.startswith(porcelain.REMOTES_PREFIX)

    def name(self):
        return translate("Operation", "Delete branch on remote")

    def preExecuteUiFlow(self):
        question = (
                self.tr("Really delete branch <b>“{0}”</b> from the remote repository?").format(escape(self.remoteBranchName))
                + "<br>"
                + translate("Global", "This cannot be undone!"))
        yield self.abortIfQuestionRejected(text=question, acceptButtonIcon=QStyle.StandardPixmap.SP_DialogDiscardButton)

        self.showRemoteLinkDialog()

    def execute(self):
        porcelain.deleteRemoteBranch(self.repo, self.remoteBranchName, self.rlpd.remoteLink)


class RenameRemoteBranch(_BaseNetTask):
    def __init__(self, rw, remoteBranchName: str):
        super().__init__(rw)

        assert not remoteBranchName.startswith(porcelain.REMOTES_PREFIX)
        remoteName, branchName = porcelain.splitRemoteBranchShorthand(remoteBranchName)
        self.remoteBranchName = remoteBranchName
        self.newBranchName = branchName  # naked name, NOT prefixed with the name of the remote

    def name(self):
        return translate("Operation", "Rename branch on remote")

    def preExecuteUiFlow(self):
        dlg = showTextInputDialog(
            self.parent(),
            self.tr("Rename remote branch “{0}”").format(escape(self.remoteBranchName)),
            self.tr("Enter new name:"),
            self.newBranchName,
            okButtonText=self.tr("Rename on remote"))
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        yield AbortIfDialogRejected(dlg)
        dlg.deleteLater()

        # Naked name, NOT prefixed with the name of the remote
        self.newBranchName = dlg.lineEdit.text()

        self.showRemoteLinkDialog()

    def execute(self):
        porcelain.renameRemoteBranch(self.repo, self.remoteBranchName, self.newBranchName, self.remoteLink)


class FetchRemote(_BaseNetTask):
    def __init__(self, rw, remoteName: str):
        super().__init__(rw)
        self.remoteName = remoteName

    def name(self):
        return translate("Operation", "Fetch remote")

    def execute(self):
        porcelain.fetchRemote(self.repo, self.remoteName, self.remoteLink)


class FetchRemoteBranch(_BaseNetTask):
    def __init__(self, rw, remoteBranchName: str):
        super().__init__(rw)
        assert not remoteBranchName.startswith(porcelain.REMOTES_PREFIX)
        self.remoteBranchName = remoteBranchName

    def name(self):
        return translate("Operation", "Fetch remote branch")

    def execute(self):
        porcelain.fetchRemoteBranch(self.repo, self.remoteBranchName, self.remoteLink)
