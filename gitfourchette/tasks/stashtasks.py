from gitfourchette import porcelain
from gitfourchette import trash
from gitfourchette import util
from gitfourchette.qt import *
from gitfourchette.tasks.repotask import RepoTask, TaskAffectsWhat
from gitfourchette.widgets.stashdialog import StashDialog
from gitfourchette.widgets.stashdialog_legacy import StashDialog_Legacy
from html import escape
import os
import pygit2


def backupStash(repo: pygit2.Repository, stashCommitId: pygit2.Oid):
    repoTrash = trash.Trash(repo)
    trashFile = repoTrash.newFile(ext=".txt", originalPath="DELETED_STASH")

    text = F"""\
To recover this stash, paste the hash below into "Repo > Recall Lost Commit" in {qAppName()}:

{stashCommitId.hex}

----------------------------------------

Original stash message below:

{repo[stashCommitId].peel(pygit2.Commit).message}
"""

    with open(trashFile, 'wt', encoding="utf-8") as f:
        f.write(text)


class NewStash(RepoTask):
    def name(self):
        return translate("Operation", "New stash")

    def refreshWhat(self):
        return TaskAffectsWhat.INDEX | TaskAffectsWhat.LOCALREFS

    @property
    def rw(self) -> 'RepoWidget':
        return self.parent()

    def flow(self, paths: list[str] | None = None):
        # TODO: Remove this try/except once libgit2 1.6 support lands in pygit2
        try:
            porcelain.pygit2VersionAtLeast((1, 11, 3), featureName="File-by-file stashing")
        except NotImplementedError as exc:
            if paths:
                yield from self._flowAbort(str(exc))
            else:
                yield from self.legacyFlow()
            return

        status = self.repo.status(untracked_files="all", ignored=False)

        if not status:
            yield from self._flowAbort(self.tr("There are no changes to stash."), "information")

        dlg = StashDialog(status, paths, self.parent())
        util.setWindowModal(dlg)
        dlg.show()
        # dlg.setMaximumHeight(dlg.height())
        yield from self._flowDialog(dlg)

        tickedFiles = dlg.tickedPaths()

        stashMessage = dlg.ui.messageEdit.text()
        keepIntact = not dlg.ui.cleanupCheckBox.isChecked()
        dlg.deleteLater()

        yield from self._flowBeginWorkerThread()
        with self.rw.fileWatcher.blockWatchingIndex():
            porcelain.newStash(self.repo, stashMessage, paths=tickedFiles)
            if not keepIntact:
                porcelain.restoreFiles(self.repo, tickedFiles)

    def legacyFlow(self):
        """
        TODO: Remove this once libgit2 1.6 support lands in pygit2
        """

        dlg = StashDialog_Legacy(self.parent())
        util.setWindowModal(dlg)
        dlg.show()
        dlg.setMaximumHeight(dlg.height())
        yield from self._flowDialog(dlg)

        stashMessage = dlg.ui.messageEdit.text()
        dlg.deleteLater()

        keepIndex = dlg.ui.keepIndexCheckBox.isChecked()
        includeUntracked = dlg.ui.includeUntrackedCheckBox.isChecked()
        includeIgnored = dlg.ui.includeIgnoredCheckBox.isChecked()

        yield from self._flowBeginWorkerThread()
        with self.rw.fileWatcher.blockWatchingIndex():
            porcelain.newStash_legacy(
                self.repo, stashMessage,
                keepIndex=keepIndex, includeUntracked=includeUntracked, includeIgnored=includeIgnored)


class ApplyStash(RepoTask):
    def name(self):
        return translate("Operation", "Apply stash")

    def refreshWhat(self):
        return TaskAffectsWhat.INDEX | TaskAffectsWhat.LOCALREFS  # LOCALREFS only changes if the stash is deleted

    def flow(self, stashCommitId: pygit2.Oid, tickDelete=True):
        stashCommit: pygit2.Commit = self.repo[stashCommitId].peel(pygit2.Commit)
        stashMessage = porcelain.getCoreStashMessage(stashCommit.message)

        question = self.tr("Do you want to apply the changes stashed in <b>“{0}”</b> to your working directory?"
                           ).format(escape(stashMessage))

        qmb = util.asyncMessageBox(self.parent(), 'question', self.name(), question,
                                   QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
                                   deleteOnClose=False)

        def updateButtonText(ticked: bool):
            okButton = qmb.button(QMessageBox.StandardButton.Ok)
            okButton.setText(self.tr("&Apply && Delete") if ticked else self.tr("&Apply && Keep"))

        deleteCheckBox = QCheckBox(self.tr("&Delete the stash if it applies cleanly"), qmb)
        deleteCheckBox.clicked.connect(updateButtonText)
        deleteCheckBox.setChecked(tickDelete)
        qmb.setCheckBox(deleteCheckBox)
        updateButtonText(tickDelete)
        yield from self._flowDialog(qmb)

        deleteAfterApply = deleteCheckBox.isChecked()
        qmb.deleteLater()

        yield from self._flowBeginWorkerThread()
        porcelain.applyStash(self.repo, stashCommitId)

        if deleteAfterApply:
            backupStash(self.repo, stashCommitId)
            porcelain.dropStash(self.repo, stashCommitId)


class DropStash(RepoTask):
    def name(self):
        return translate("Operation", "Drop stash")

    def refreshWhat(self):
        return TaskAffectsWhat.LOCALREFS

    def flow(self, stashCommitId: pygit2.Oid):
        stashCommit: pygit2.Commit = self.repo[stashCommitId].peel(pygit2.Commit)
        stashMessage = porcelain.getCoreStashMessage(stashCommit.message)
        yield from self._flowConfirm(
            text=self.tr("Really delete stash <b>“{0}”</b>?").format(stashMessage),
            verb=self.tr("Delete stash"),
            buttonIcon=QStyle.StandardPixmap.SP_DialogDiscardButton)

        yield from self._flowBeginWorkerThread()
        backupStash(self.repo, stashCommitId)
        porcelain.dropStash(self.repo, stashCommitId)
