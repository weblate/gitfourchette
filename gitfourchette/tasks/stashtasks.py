# -----------------------------------------------------------------------------
# Copyright (C) 2024 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

from gitfourchette.nav import NavLocator
from gitfourchette.porcelain import *
from gitfourchette.qt import *
from gitfourchette.tasks.repotask import AbortTask, RepoTask, TaskEffects, TaskPrereqs
from gitfourchette.trash import Trash
from gitfourchette.toolbox import *
from gitfourchette.forms.stashdialog import StashDialog


def backupStash(repo: Repo, stashCommitId: Oid):
    trashFile = Trash.instance().newFile(repo.workdir, ext=".txt", originalPath="DELETED_STASH")

    if not trashFile:
        return

    text = F"""\
To recover this stash, paste the hash below into "Repo > Recall Lost Commit" in {qAppName()}:

{stashCommitId}

----------------------------------------

Original stash message below:

{repo.peel_commit(stashCommitId).message}
"""

    with open(trashFile, "w", encoding="utf-8") as f:
        f.write(text)


class NewStash(RepoTask):
    def prereqs(self):
        # libgit2 will refuse to create a stash if there are conflicts (NoConflicts)
        # libgit2 will refuse to create a stash if there are no commits at all (NoUnborn)
        return TaskPrereqs.NoConflicts | TaskPrereqs.NoUnborn

    def flow(self, paths: list[str] | None = None):
        status = self.repo.status(untracked_files="all", ignored=False)

        if not status:
            raise AbortTask(self.tr("There are no uncommitted changes to stash."), "information")

        # Prevent stashing any submodules
        with Benchmark("Query submodules"):
            for submodulePath in self.repo.listall_submodules_fast():
                status.pop(submodulePath, None)

        if not status:
            raise AbortTask(self.tr("There are no uncommitted changes to stash (submodules cannot be stashed)."), "information")

        dlg = StashDialog(status, paths or [], self.parentWidget())
        dlg.setWindowModality(Qt.WindowModality.WindowModal)
        dlg.show()
        yield from self.flowDialog(dlg)

        tickedFiles = dlg.tickedPaths()

        stashMessage = dlg.ui.messageEdit.text()
        keepIntact = dlg.ui.keepCheckBox.isChecked()
        dlg.deleteLater()

        yield from self.flowEnterWorkerThread()
        self.effects |= TaskEffects.Refs

        self.repo.create_stash(stashMessage, paths=tickedFiles)

        if not keepIntact:
            self.effects |= TaskEffects.Workdir
            self.repo.restore_files_from_head(tickedFiles)

        self.postStatus = self.tr("%n files stashed.", "please omit %n in singular form", len(tickedFiles))


class ApplyStash(RepoTask):
    def prereqs(self):
        # libgit2 will refuse to apply a stash if there are conflicts (NoConflicts)
        return TaskPrereqs.NoConflicts | TaskPrereqs.NoStagedChanges

    def flow(self, stashCommitId: Oid, tickDelete=True):
        stashCommit: Commit = self.repo.peel_commit(stashCommitId)
        stashMessage = strip_stash_message(stashCommit.message)

        question = self.tr("Do you want to apply the changes stashed in {0} to your working directory?"
                           ).format(bquoe(stashMessage))

        qmb = asyncMessageBox(self.parentWidget(), 'question', self.name(), question,
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
        yield from self.flowDialog(qmb)

        deleteAfterApply = deleteCheckBox.isChecked()
        qmb.deleteLater()

        yield from self.flowEnterWorkerThread()
        self.effects |= TaskEffects.Workdir
        self.jumpTo = NavLocator.inWorkdir()

        self.repo.stash_apply_id(stashCommitId)

        self.postStatus = self.tr("Stash {0} applied.").format(tquoe(stashMessage))

        if self.repo.index.conflicts:
            yield from self.flowEnterUiThread()
            self.postStatus = self.tr("Stash {0} applied, with conflicts.").format(tquoe(stashMessage))
            message = [self.tr("Applying the stash {0} has caused merge conflicts "
                               "because your files have diverged since they were stashed."
                               ).format(bquoe(stashMessage))]
            if deleteAfterApply:
                message.append(self.tr("The stash wasn’t deleted in case you need to re-apply it later."))
            showWarning(self.parentWidget(), self.tr("Conflicts caused by stash application"), paragraphs(message))
            return

        if deleteAfterApply:
            self.effects |= TaskEffects.Refs
            backupStash(self.repo, stashCommitId)
            self.repo.stash_drop_id(stashCommitId)
            self.postStatus = self.tr("Stash {0} applied and deleted.").format(tquoe(stashMessage))


class DropStash(RepoTask):
    def flow(self, stashCommitId: Oid):
        stashCommit = self.repo.peel_commit(stashCommitId)
        stashMessage = strip_stash_message(stashCommit.message)
        yield from self.flowConfirm(
            text=self.tr("Really delete stash {0}?").format(bquoe(stashMessage)),
            verb=self.tr("Delete stash"),
            buttonIcon="SP_DialogDiscardButton")

        yield from self.flowEnterWorkerThread()
        self.effects |= TaskEffects.Refs

        backupStash(self.repo, stashCommitId)
        self.repo.stash_drop_id(stashCommitId)
        self.postStatus = self.tr("Stash {0} deleted.").format(tquoe(stashMessage))
