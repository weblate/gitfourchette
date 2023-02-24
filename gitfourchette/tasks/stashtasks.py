from gitfourchette import porcelain
from gitfourchette import util
from gitfourchette.qt import *
from gitfourchette.tasks.repotask import RepoTask, TaskAffectsWhat
from gitfourchette.widgets.stashdialog import StashDialog
from html import escape
import os
import pygit2


class NewStash(RepoTask):
    def name(self):
        return translate("Operation", "New stash")

    def refreshWhat(self):
        return TaskAffectsWhat.INDEX | TaskAffectsWhat.LOCALREFS

    @property
    def rw(self) -> 'RepoWidget':
        return self.parent()

    def flow(self):
        dlg = StashDialog(self.parent())
        util.setWindowModal(dlg)
        dlg.show()
        dlg.setMaximumHeight(dlg.height())
        yield from self._flowDialog(dlg)

        stashMessage = dlg.ui.messageEdit.text()
        stashFlags = ""
        if dlg.ui.keepIndexCheckBox.isChecked():
            stashFlags += "k"
        if dlg.ui.includeUntrackedCheckBox.isChecked():
            stashFlags += "u"
        if dlg.ui.includeIgnoredCheckBox.isChecked():
            stashFlags += "i"
        dlg.deleteLater()

        yield from self._flowBeginWorkerThread()
        with self.rw.fileWatcher.blockWatchingIndex():
            porcelain.newStash(self.repo, stashMessage, stashFlags)


class ApplyStash(RepoTask):
    def name(self):
        return translate("Operation", "Apply stash")

    def refreshWhat(self):
        return TaskAffectsWhat.INDEX

    def flow(self, stashCommitId: pygit2.Oid, confirmFirst=False):
        if confirmFirst:
            stashCommit: pygit2.Commit = self.repo[stashCommitId].peel(pygit2.Commit)
            stashMessage = porcelain.getCoreStashMessage(stashCommit.message)
            question = self.tr("Do you want to apply the changes stashed in <b>“{0}”</b> to your working directory?"
                               ).format(escape(stashMessage))
            yield from self._flowConfirm(text=question)

        yield from self._flowBeginWorkerThread()
        porcelain.applyStash(self.repo, stashCommitId)


class PopStash(RepoTask):
    def name(self):
        return translate("Operation", "Pop stash")

    def refreshWhat(self):
        return TaskAffectsWhat.INDEX | TaskAffectsWhat.LOCALREFS

    def flow(self, stashCommitId: pygit2.Oid):
        yield from self._flowBeginWorkerThread()
        porcelain.popStash(self.repo, stashCommitId)


class DropStash(RepoTask):
    def name(self):
        return translate("Operation", "Drop stash")

    def refreshWhat(self):
        return TaskAffectsWhat.LOCALREFS

    def flow(self, stashCommitId: pygit2.Oid):
        stashCommit: pygit2.Commit = self.repo[stashCommitId].peel(pygit2.Commit)
        stashMessage = porcelain.getCoreStashMessage(stashCommit.message)
        question = self.tr("Really delete stash <b>“{0}”</b>?").format(stashMessage)
        yield from self._flowConfirm(text=question)

        yield from self._flowBeginWorkerThread()
        porcelain.dropStash(self.repo, stashCommitId)
