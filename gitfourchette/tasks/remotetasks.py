"""
Remote management tasks.
"""

from gitfourchette import porcelain
from gitfourchette import util
from gitfourchette.qt import *
from gitfourchette.tasks.repotask import RepoTask, TaskAffectsWhat
from gitfourchette.widgets.remotedialog import RemoteDialog
from html import escape


class NewRemote(RepoTask):
    def name(self):
        return translate("Operation", "Add remote")

    def refreshWhat(self) -> TaskAffectsWhat:
        return TaskAffectsWhat.REMOTES

    def flow(self):
        dlg = RemoteDialog(False, "", "", self.parent())
        util.setWindowModal(dlg)
        dlg.show()
        dlg.setMaximumHeight(dlg.height())
        yield from self._flowDialog(dlg)

        newRemoteName = dlg.ui.nameEdit.text()
        newRemoteUrl = dlg.ui.urlEdit.text()
        dlg.deleteLater()

        yield from self._flowBeginWorkerThread()
        porcelain.newRemote(self.repo, newRemoteName, newRemoteUrl)


class EditRemote(RepoTask):
    def name(self):
        return translate("Operation", "Edit remote")

    def refreshWhat(self) -> TaskAffectsWhat:
        return TaskAffectsWhat.REMOTES

    def flow(self, oldRemoteName: str):
        oldRemoteUrl = self.repo.remotes[oldRemoteName].url

        dlg = RemoteDialog(True, oldRemoteName, oldRemoteUrl, self.parent())
        util.setWindowModal(dlg)
        dlg.show()
        dlg.setMaximumHeight(dlg.height())
        yield from self._flowDialog(dlg)

        newRemoteName = dlg.ui.nameEdit.text()
        newRemoteUrl = dlg.ui.urlEdit.text()
        dlg.deleteLater()

        yield from self._flowBeginWorkerThread()
        porcelain.editRemote(self.repo, oldRemoteName, newRemoteName, newRemoteUrl)


class DeleteRemote(RepoTask):
    def name(self):
        return translate("Operation", "Remove remote")

    def refreshWhat(self) -> TaskAffectsWhat:
        return TaskAffectsWhat.REMOTES

    def flow(self, remoteName: str):
        yield from self._flowConfirm(
            text=util.paragraphs(
                self.tr("Really remove remote <b>“{0}”</b>?").format(escape(remoteName)),
                self.tr("This will merely detach the remote from your local repository. "
                        "The remote server itself will not be affected.")),
            verb=self.tr("Remove remote", "Button label"),
            buttonIcon=QStyle.StandardPixmap.SP_DialogDiscardButton)

        yield from self._flowBeginWorkerThread()
        porcelain.deleteRemote(self.repo, remoteName)
