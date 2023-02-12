from gitfourchette import porcelain
from gitfourchette.qt import *
from gitfourchette.tasks.repotask import RepoTask, TaskAffectsWhat, AbortIfDialogRejected
from gitfourchette.trash import Trash
from gitfourchette import util
from gitfourchette.widgets.stashdialog import StashDialog
from gitfourchette.widgets.brandeddialog import showTextInputDialog
from html import escape
import os
import pygit2


class NewStashTask(RepoTask):
    def __init__(self, rw):
        super().__init__(rw)
        self.newRemoteName = ""
        self.newRemoteUrl = ""

    def name(self):
        return translate("Operation", "New stash")

    def refreshWhat(self):
        return TaskAffectsWhat.INDEX | TaskAffectsWhat.LOCALREFS

    def preExecuteUiFlow(self):
        dlg = StashDialog(self.parent())
        util.setWindowModal(dlg)
        dlg.show()
        dlg.setMaximumHeight(dlg.height())
        yield AbortIfDialogRejected(dlg)
        dlg.deleteLater()

        self.stashMessage = dlg.ui.messageEdit.text()
        self.stashFlags = ""
        if dlg.ui.keepIndexCheckBox.isChecked():
            self.stashFlags += "k"
        if dlg.ui.includeUntrackedCheckBox.isChecked():
            self.stashFlags += "u"
        if dlg.ui.includeIgnoredCheckBox.isChecked():
            self.stashFlags += "i"

    def execute(self):
        with self.rw.fileWatcher.blockWatchingIndex():
            porcelain.newStash(self.repo, self.stashMessage, self.stashFlags)


class ApplyStashTask(RepoTask):
    def __init__(self, rw, stashCommitId: pygit2.Oid):
        super().__init__(rw)
        self.stashCommitId = stashCommitId

    def name(self):
        return translate("Operation", "Apply stash")

    def refreshWhat(self):
        return TaskAffectsWhat.INDEX

    def execute(self):
        porcelain.applyStash(self.repo, self.stashCommitId)


class PopStashTask(ApplyStashTask):
    def name(self):
        return translate("Operation", "Pop stash")

    def refreshWhat(self):
        return TaskAffectsWhat.INDEX | TaskAffectsWhat.LOCALREFS

    def execute(self):
        porcelain.popStash(self.repo, self.stashCommitId)


class DropStashTask(RepoTask):
    def __init__(self, rw, stashCommitId: pygit2.Oid):
        super().__init__(rw)
        self.stashCommitId = stashCommitId

    def name(self):
        return translate("Operation", "Drop stash")

    def refreshWhat(self):
        return TaskAffectsWhat.LOCALREFS

    def preExecuteUiFlow(self):
        stashCommit: pygit2.Commit = self.repo[self.stashCommitId].peel(pygit2.Commit)
        stashMessage = porcelain.getCoreStashMessage(stashCommit.message)
        question = self.tr("Really delete stash <b>“{0}”</b>?").format(stashMessage)
        yield self.abortIfQuestionRejected(text=question)

    def execute(self):
        porcelain.dropStash(self.repo, self.stashCommitId)
