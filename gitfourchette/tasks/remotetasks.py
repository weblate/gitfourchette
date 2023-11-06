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
        yield from self._flowDialog(dlg)

        newRemoteName = dlg.ui.nameEdit.text()
        newRemoteUrl = dlg.ui.urlEdit.text()
        fetchAfterAdd = dlg.ui.fetchAfterAddCheckBox.isChecked()
        dlg.deleteLater()

        yield from self._flowBeginWorkerThread()
        porcelain.newRemote(self.repo, newRemoteName, newRemoteUrl)

        if fetchAfterAdd:
            yield from self._flowExitWorkerThread()

            from gitfourchette.tasks import FetchRemote
            yield from self._flowSubtask(FetchRemote, newRemoteName)


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
        dlg.resize(512, 128)
        dlg.show()
        dlg.setMaximumHeight(dlg.height())
        yield from self._flowDialog(dlg)

        newRemoteName = dlg.ui.nameEdit.text()
        newRemoteUrl = dlg.ui.urlEdit.text()
        newRemoteKeyfile = dlg.privateKeyFilePath
        dlg.deleteLater()

        yield from self._flowBeginWorkerThread()
        porcelain.editRemote(self.repo, oldRemoteName, newRemoteName, newRemoteUrl)
        repoconfig.setRemoteKeyFile(self.repo, newRemoteName, newRemoteKeyfile)


class DeleteRemote(RepoTask):
    def effects(self) -> TaskEffects:
        return TaskEffects.Refs | TaskEffects.Remotes

    def flow(self, remoteName: str):
        yield from self._flowConfirm(
            text=paragraphs(
                self.tr("Really remove remote <b>“{0}”</b>?").format(escape(remoteName)),
                self.tr("This will merely detach the remote from your local repository. "
                        "The remote server itself will not be affected.")),
            verb=self.tr("Remove remote", "Button label"),
            buttonIcon=QStyle.StandardPixmap.SP_DialogDiscardButton)

        yield from self._flowBeginWorkerThread()
        porcelain.deleteRemote(self.repo, remoteName)
