"""
Remote management tasks.
"""

from gitfourchette import porcelain
from gitfourchette.qt import *
from gitfourchette.tasks.repotask import RepoTask, TaskAffectsWhat, AbortIfDialogRejected
from gitfourchette.trash import Trash
from gitfourchette import util
from gitfourchette.widgets.remotedialog import RemoteDialog
from gitfourchette.widgets.brandeddialog import showTextInputDialog
from html import escape
import os
import pygit2


class NewRemoteTask(RepoTask):
    def __init__(self, rw):
        super().__init__(rw)
        self.newRemoteName = ""
        self.newRemoteUrl = ""

    def name(self):
        return translate("Operation", "Add remote")

    def refreshWhat(self) -> TaskAffectsWhat:
        return TaskAffectsWhat.REMOTES

    def preExecuteUiFlow(self):
        dlg = RemoteDialog(False, "", "", self.parent())
        util.setWindowModal(dlg)
        dlg.show()
        dlg.setMaximumHeight(dlg.height())
        yield AbortIfDialogRejected(dlg)
        dlg.deleteLater()

        self.newRemoteName = dlg.ui.nameEdit.text()
        self.newRemoteUrl = dlg.ui.urlEdit.text()

    def execute(self):
        porcelain.newRemote(self.repo, self.newRemoteName, self.newRemoteUrl)


class EditRemoteTask(RepoTask):
    def __init__(self, rw, remoteName):
        super().__init__(rw)
        self.oldRemoteName = remoteName
        self.newRemoteName = remoteName
        self.newRemoteUrl = ""

    def name(self):
        return translate("Operation", "Edit remote")

    def refreshWhat(self) -> TaskAffectsWhat:
        return TaskAffectsWhat.REMOTES

    def preExecuteUiFlow(self):
        oldRemoteUrl = self.repo.remotes[self.oldRemoteName].url

        dlg = RemoteDialog(True, self.oldRemoteName, oldRemoteUrl, self.parent())
        util.setWindowModal(dlg)
        dlg.show()
        dlg.setMaximumHeight(dlg.height())
        yield AbortIfDialogRejected(dlg)
        dlg.deleteLater()

        self.newRemoteName = dlg.ui.nameEdit.text()
        self.newRemoteUrl = dlg.ui.urlEdit.text()

    def execute(self):
        porcelain.editRemote(self.repo, self.oldRemoteName, self.newRemoteName, self.newRemoteUrl)


class DeleteRemoteTask(RepoTask):
    def __init__(self, rw, remoteName):
        super().__init__(rw)
        self.remoteName = remoteName

    def name(self):
        return translate("Operation", "Delete remote")

    def refreshWhat(self) -> TaskAffectsWhat:
        return TaskAffectsWhat.REMOTES

    def preExecuteUiFlow(self):
        yield self.abortIfQuestionRejected(
            text=self.tr("Really delete remote <b>“{0}”</b>?").format(escape(self.remoteName)),
            acceptButtonIcon=QStyle.StandardPixmap.SP_DialogDiscardButton)

    def execute(self):
        porcelain.deleteRemote(self.repo, self.remoteName)



