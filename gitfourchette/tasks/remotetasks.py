"""
Remote management tasks.
"""

from gitfourchette.forms.remotedialog import RemoteDialog
from gitfourchette.qt import *
from gitfourchette.tasks.repotask import RepoTask, TaskEffects
from gitfourchette.toolbox import *


class NewRemote(RepoTask):
    def flow(self):
        existingRemotes = [r.name for r in self.repo.remotes]

        dlg = RemoteDialog(
            edit=False,
            name="",
            url="",
            customKeyFile="",
            existingRemotes=existingRemotes,
            parent=self.parentWidget())

        dlg.setWindowModality(Qt.WindowModality.WindowModal)
        dlg.show()
        dlg.setMaximumHeight(dlg.height())
        yield from self.flowDialog(dlg)

        newRemoteName = dlg.ui.nameEdit.text()
        newRemoteUrl = dlg.ui.urlEdit.text()
        fetchAfterAdd = dlg.ui.fetchAfterAddCheckBox.isChecked()
        dlg.deleteLater()

        yield from self.flowEnterWorkerThread()
        self.effects |= TaskEffects.Refs | TaskEffects.Remotes
        self.repo.create_remote(newRemoteName, newRemoteUrl)

        if fetchAfterAdd:
            yield from self.flowEnterUiThread()

            from gitfourchette.tasks import FetchRemote
            yield from self.flowSubtask(FetchRemote, newRemoteName)


class EditRemote(RepoTask):
    def flow(self, oldRemoteName: str):
        oldRemoteUrl = self.repo.remotes[oldRemoteName].url

        existingRemotes = [r.name for r in self.repo.remotes]
        existingRemotes.remove(oldRemoteName)

        dlg = RemoteDialog(
            edit=True,
            name=oldRemoteName,
            url=oldRemoteUrl,
            customKeyFile=self.repoModel.prefs.getRemoteKeyFile(oldRemoteName),
            existingRemotes=existingRemotes,
            parent=self.parentWidget())

        dlg.setWindowModality(Qt.WindowModality.WindowModal)
        dlg.setFixedHeight(dlg.sizeHint().height())
        dlg.show()
        yield from self.flowDialog(dlg)

        newRemoteName = dlg.ui.nameEdit.text()
        newRemoteUrl = dlg.ui.urlEdit.text()
        newRemoteKeyfile = dlg.privateKeyFilePath
        dlg.deleteLater()

        yield from self.flowEnterWorkerThread()
        self.effects |= TaskEffects.Refs | TaskEffects.Remotes
        self.repo.edit_remote(oldRemoteName, newRemoteName, newRemoteUrl)
        self.repoModel.prefs.setRemoteKeyFile(newRemoteName, newRemoteKeyfile)


class DeleteRemote(RepoTask):
    def flow(self, remoteName: str):
        yield from self.flowConfirm(
            text=paragraphs(
                self.tr("Really remove remote {0}?"),
                self.tr("This will merely detach the remote from your local repository. "
                        "The remote server itself will not be affected.")
            ).format(bquo(remoteName)),
            verb=self.tr("Remove remote", "Button label"),
            buttonIcon="SP_DialogDiscardButton")

        yield from self.flowEnterWorkerThread()
        self.effects |= TaskEffects.Refs | TaskEffects.Remotes
        self.repo.delete_remote(remoteName)
