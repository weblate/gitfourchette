"""
Remote access tasks.
"""

from gitfourchette.porcelain import *
from gitfourchette.qt import *
from gitfourchette.tasks.repotask import RepoTask, TaskEffects
from gitfourchette.toolbox import *
from gitfourchette.forms.brandeddialog import showTextInputDialog
from gitfourchette.forms.remotelinkprogressdialog import RemoteLinkProgressDialog
import contextlib


class _BaseNetTask(RepoTask):
    remoteLinkDialog: RemoteLinkProgressDialog | None

    def __init__(self, parent):
        super().__init__(parent)
        self.remoteLinkDialog = None

    def effects(self) -> TaskEffects:
        return TaskEffects.Remotes

    def _showRemoteLinkDialog(self):
        assert not self.remoteLinkDialog
        assert onAppThread()
        self.remoteLinkDialog = RemoteLinkProgressDialog(self.parentWidget())

    def cleanup(self):
        assert onAppThread()
        if self.remoteLinkDialog:
            self.remoteLinkDialog.close()
            self.remoteLinkDialog.deleteLater()
            self.remoteLinkDialog = None

    @property
    def remoteLink(self):
        return self.remoteLinkDialog.remoteLink


class DeleteRemoteBranch(_BaseNetTask):
    def flow(self, remoteBranchShorthand: str):
        assert not remoteBranchShorthand.startswith(GIT_REMOTES_PREFIX)

        remoteName, _ = split_remote_branch_shorthand(remoteBranchShorthand)

        text = paragraphs(
            self.tr("Really delete branch <b>“{0}”</b> "
                    "from the remote repository?").format(escape(remoteBranchShorthand)),
            self.tr("The remote branch will disappear for all users of remote “{0}”.").format(escape(remoteName))
            + " " + translate("Global", "This cannot be undone!"))
        verb = self.tr("Delete on remote")
        yield from self._flowConfirm(text=text, verb=verb, buttonIcon=QStyle.StandardPixmap.SP_DialogDiscardButton)

        self._showRemoteLinkDialog()

        yield from self._flowBeginWorkerThread()
        self.remoteLink.discoverKeyFiles(self.repo.remotes[remoteName])
        self.repo.delete_remote_branch(remoteBranchShorthand, self.remoteLink)


class RenameRemoteBranch(_BaseNetTask):
    def flow(self, remoteBranchName: str):
        assert not remoteBranchName.startswith(GIT_REMOTES_PREFIX)
        remoteName, branchName = split_remote_branch_shorthand(remoteBranchName)
        newBranchName = branchName  # naked name, NOT prefixed with the name of the remote

        reservedNames = self.repo.listall_remote_branches().get(remoteName, [])
        with contextlib.suppress(ValueError):
            reservedNames.remove(branchName)
        nameTaken = self.tr("This name is already taken by another branch on this remote.")

        dlg = showTextInputDialog(
            self.parentWidget(),
            self.tr("Rename remote branch “{0}”").format(escape(remoteBranchName)),
            self.tr("Enter new name:"),
            newBranchName,
            okButtonText=self.tr("Rename on remote"),
            validate=lambda name: nameValidationMessage(name, reservedNames, nameTaken),
            deleteOnClose=False)

        yield from self._flowDialog(dlg)
        dlg.deleteLater()

        # Naked name, NOT prefixed with the name of the remote
        newBranchName = dlg.lineEdit.text()

        self._showRemoteLinkDialog()

        yield from self._flowBeginWorkerThread()
        self.remoteLink.discoverKeyFiles(self.repo.remotes[remoteName])
        self.repo.rename_remote_branch(remoteBranchName, newBranchName, self.remoteLink)


class FetchRemote(_BaseNetTask):
    def flow(self, remoteName: str):
        self._showRemoteLinkDialog()

        yield from self._flowBeginWorkerThread()
        self.remoteLink.discoverKeyFiles(self.repo.remotes[remoteName])
        self.repo.fetch_remote(remoteName, self.remoteLink)


class FetchRemoteBranch(_BaseNetTask):
    def flow(self, remoteBranchName: str = ""):
        if not remoteBranchName:
            branchName = self.repo.head_branch_shorthand

            try:
                branch = self.repo.branches.local[branchName]
            except KeyError:
                yield from self._flowAbort(self.tr("Please switch to a local branch before performing this action."))

            if not branch.upstream:
                yield from self._flowAbort(self.tr("Can’t fetch remote changes on “{0}” because it isn’t tracking a remote branch.").format(branch.shorthand))

            remoteBranchName = branch.upstream.shorthand

        self._showRemoteLinkDialog()

        yield from self._flowBeginWorkerThread()

        remoteName, _ = split_remote_branch_shorthand(remoteBranchName)
        self.remoteLink.discoverKeyFiles(self.repo.remotes[remoteName])
        self.repo.fetch_remote_branch(remoteBranchName, self.remoteLink)
