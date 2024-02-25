"""
Remote management tasks.
"""

from gitfourchette import porcelain
from gitfourchette import repoconfig
from gitfourchette.qt import *
from gitfourchette.tasks.repotask import RepoTask, TaskEffects
from gitfourchette.toolbox import *
from gitfourchette.forms.remotedialog import RemoteDialog


class NewRemote(RepoTask):
    def effects(self) -> TaskEffects:
        return TaskEffects.Refs | TaskEffects.Remotes

    def flow(self):
        existingRemotes = [r.name for r in self.repo.remotes]

        dlg = RemoteDialog(
            edit=False,
            remoteName="",
            remoteURL="",
            customKeyFile="",
            existingRemotes=existingRemotes,
            parent=self.parentWidget())

        setWindowModal(dlg)
        dlg.show()
        dlg.setMaximumHeight(dlg.height())
        yield from self.flowDialog(dlg)

        newRemoteName = dlg.ui.nameEdit.text()
        newRemoteUrl = dlg.ui.urlEdit.text()
        fetchAfterAdd = dlg.ui.fetchAfterAddCheckBox.isChecked()
        dlg.deleteLater()

        yield from self.flowEnterWorkerThread()
        self.repo.create_remote(newRemoteName, newRemoteUrl)

        if fetchAfterAdd:
            yield from self.flowEnterUiThread()

            from gitfourchette.tasks import FetchRemote
            yield from self.flowSubtask(FetchRemote, newRemoteName)


class EditRemote(RepoTask):
    def effects(self) -> TaskEffects:
        return TaskEffects.Refs | TaskEffects.Remotes

    def flow(self, oldRemoteName: str):
        oldRemoteUrl = self.repo.remotes[oldRemoteName].url

        existingRemotes = [r.name for r in self.repo.remotes]
        existingRemotes.remove(oldRemoteName)

        dlg = RemoteDialog(
            edit=True,
            remoteName=oldRemoteName,
            remoteURL=oldRemoteUrl,
            customKeyFile=repoconfig.getRemoteKeyFile(self.repo, oldRemoteName),
            existingRemotes=existingRemotes,
            parent=self.parentWidget())

        setWindowModal(dlg)
        dlg.setFixedHeight(dlg.sizeHint().height())
        dlg.show()
        yield from self.flowDialog(dlg)

        newRemoteName = dlg.ui.nameEdit.text()
        newRemoteUrl = dlg.ui.urlEdit.text()
        newRemoteKeyfile = dlg.privateKeyFilePath
        dlg.deleteLater()

        yield from self.flowEnterWorkerThread()
        self.repo.edit_remote(oldRemoteName, newRemoteName, newRemoteUrl)
        repoconfig.setRemoteKeyFile(self.repo, newRemoteName, newRemoteKeyfile)

        if newRemoteName != oldRemoteName:
            self.repo.scrub_empty_config_section("remote", oldRemoteName)


class DeleteRemote(RepoTask):
    def effects(self) -> TaskEffects:
        return TaskEffects.Refs | TaskEffects.Remotes

    def flow(self, remoteName: str):
        yield from self.flowConfirm(
            text=paragraphs(
                self.tr("Really remove remote {0}?"),
                self.tr("This will merely detach the remote from your local repository. "
                        "The remote server itself will not be affected.")
            ).format(bquo(remoteName)),
            verb=self.tr("Remove remote", "Button label"),
            buttonIcon=QStyle.StandardPixmap.SP_DialogDiscardButton)

        yield from self.flowEnterWorkerThread()
        self.repo.delete_remote(remoteName)
        self.repo.scrub_empty_config_section("remote", remoteName)
