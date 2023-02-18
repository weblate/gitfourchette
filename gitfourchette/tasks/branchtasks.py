from gitfourchette import porcelain
from gitfourchette.qt import *
from gitfourchette.tasks.repotask import RepoTask, TaskAffectsWhat, ReenterWhenDialogFinished, AbortIfDialogRejected
from gitfourchette.trash import Trash
from gitfourchette import util
from gitfourchette.widgets.stashdialog import StashDialog
from gitfourchette.widgets.brandeddialog import showTextInputDialog
from gitfourchette.widgets.newbranchdialog import NewBranchDialog
from gitfourchette.widgets.trackedbranchdialog import TrackedBranchDialog
from html import escape
import os
import pygit2


class SwitchBranch(RepoTask):
    def __init__(self, rw, newBranch: str):
        super().__init__(rw)
        self.newBranch = newBranch
        assert not self.newBranch.startswith("refs/heads/")

    def name(self):
        return translate("Operation", "Switch to branch")

    def execute(self):
        porcelain.checkoutLocalBranch(self.repo, self.newBranch)


class RenameBranch(RepoTask):
    def __init__(self, rw, oldBranchName: str):
        super().__init__(rw)
        self.oldBranchName = oldBranchName
        self.newBranchName = oldBranchName
        assert not self.oldBranchName.startswith("refs/heads/")

    def name(self):
        return translate("Operation", "Rename local branch")

    def preExecuteUiFlow(self):
        dlg = showTextInputDialog(
            self.parent(),
            self.tr("Rename local branch “{0}”").format(escape(self.oldBranchName)),
            self.tr("Enter new name:"),
            self.newBranchName,
            okButtonText=self.tr("Rename"))
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        yield AbortIfDialogRejected(dlg)
        dlg.deleteLater()
        self.newBranchName = dlg.lineEdit.text()

    def execute(self):
        porcelain.renameBranch(self.repo, self.oldBranchName, self.newBranchName)

    def refreshWhat(self):
        return TaskAffectsWhat.LOCALREFS


class DeleteBranch(RepoTask):
    def __init__(self, rw, localBranchName: str):
        super().__init__(rw)
        self.localBranchName = localBranchName
        assert not localBranchName.startswith("refs/heads/")

    def name(self):
        return translate("Operation", "Delete local branch")

    def preExecuteUiFlow(self):
        question = (
                self.tr("Really delete local branch <b>“{0}”</b>?").format(escape(self.localBranchName))
                + "<br>"
                + translate("Global", "This cannot be undone!"))
        yield self.abortIfQuestionRejected(text=question, acceptButtonIcon=QStyle.StandardPixmap.SP_DialogDiscardButton)

    def execute(self):
        porcelain.deleteBranch(self.repo, self.localBranchName)

    def refreshWhat(self):
        return TaskAffectsWhat.LOCALREFS


class NewBranch(RepoTask):
    def __init__(self, rw):
        super().__init__(rw)

    def name(self):
        return translate("Operation", "New local branch")

    def preExecuteUiFlow(self):
        self.tip = porcelain.getHeadCommit(self.repo).oid
        tip = self.tip

        HEADS_PREFIX = "refs/heads/"
        REMOTES_PREFIX = "refs/remotes/"

        initialName = ""
        trackingCandidates = []

        # If we're creating a branch at the tip of the current branch, default to its name
        if (not self.repo.head_is_unborn
                and not self.repo.head_is_detached
                and self.repo.head.target == tip):
            initialName = self.repo.head.shorthand

        refsPointingHere = porcelain.mapCommitsToReferences(self.repo)[tip]

        # Collect remote-tracking branch candidates and set initialName
        for r in refsPointingHere:
            if r.startswith(HEADS_PREFIX):
                branchName = r.removeprefix(HEADS_PREFIX)
                if not initialName:
                    initialName = branchName

                branch = self.repo.branches[branchName]
                if branch.upstream and branch.upstream.shorthand not in trackingCandidates:
                    trackingCandidates.append(branch.upstream.shorthand)

            elif r.startswith(REMOTES_PREFIX):
                shorthand = r.removeprefix(REMOTES_PREFIX)
                if not initialName:
                    _, initialName = porcelain.splitRemoteBranchShorthand(shorthand)
                if shorthand not in trackingCandidates:
                    trackingCandidates.append(shorthand)

        commitMessage = porcelain.getCommitMessage(self.repo, tip)
        commitMessage, junk = util.messageSummary(commitMessage)

        dlg = NewBranchDialog(
            initialName,
            util.shortHash(tip),
            commitMessage,
            trackingCandidates=trackingCandidates,
            forbiddenBranchNames=[""] + self.repo.listall_branches(pygit2.GIT_BRANCH_LOCAL),
            parent=self.parent())

        util.setWindowModal(dlg)
        dlg.show()
        dlg.setMaximumHeight(dlg.height())
        yield AbortIfDialogRejected(dlg)
        dlg.deleteLater()

        self.localName = dlg.ui.nameEdit.text()
        self.trackingBranch = ""
        self.switchTo = dlg.ui.switchToBranchCheckBox.isChecked()
        if dlg.ui.trackRemoteBranchCheckBox.isChecked():
            self.trackingBranch = dlg.ui.trackRemoteBranchComboBox.currentText()

    def execute(self):
        # Create local branch
        porcelain.newBranchFromCommit(self.repo, self.localName, self.tip, switchTo=False)

        # Optionally make it track a remote branch
        if self.trackingBranch:
            porcelain.editTrackingBranch(self.repo, self.localName, self.trackingBranch)

        # Switch to it last (if user wants to)
        if self.switchTo:
            porcelain.checkoutLocalBranch(self.repo, self.localName)

    def refreshWhat(self):
        return TaskAffectsWhat.LOCALREFS


class NewBranchFromBranch(RepoTask):
    def __init__(self, rw, originalBranchName: str):
        super().__init__(rw)
        self.originalBranchName = originalBranchName
        self.newLocalBranchName = originalBranchName

    def refreshWhat(self):
        return TaskAffectsWhat.LOCALREFS


class NewTrackingBranch(RepoTask):
    def __init__(self, rw, remoteBranchName: str):
        super().__init__(rw)
        self.remoteBranchName = remoteBranchName
        self.localBranchName = remoteBranchName[remoteBranchName.rfind('/') + 1:]

    def name(self):
        return translate("Operation", "New local branch")

    def preExecuteUiFlow(self):
        # TODO: Reuse NewBranchDialog
        name = self.remoteBranchName

        dlg = showTextInputDialog(
            self.parent(),
            self.tr("New branch tracking “{0}”").format(escape(name)),
            self.tr("Enter name for a new local branch that will<br>track remote branch “{0}”:").format(escape(name)),
            self.localBranchName,
            okButtonText=self.tr("Create"))

        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        yield AbortIfDialogRejected(dlg)

        dlg.deleteLater()
        self.localBranchName = dlg.lineEdit.text()

    def execute(self):
        assert not self.localBranchName.startswith("refs/heads/")
        porcelain.newTrackingBranch(self.repo, self.localBranchName, self.remoteBranchName)

    def refreshWhat(self):
        return TaskAffectsWhat.LOCALREFS


class EditTrackedBranch(RepoTask):
    def __init__(self, rw, localBranchName: str):
        super().__init__(rw)
        self.localBranchName = localBranchName
        self.remoteBranchName = ""

    def name(self):
        return translate("Operation", "Change remote branch tracked by local branch")

    def preExecuteUiFlow(self):
        dlg = TrackedBranchDialog(self.repo, self.localBranchName, self.parent())
        util.setWindowModal(dlg)
        dlg.show()
        yield AbortIfDialogRejected(dlg)

        dlg.deleteLater()
        self.remoteBranchName = dlg.newTrackedBranchName

        # Bail if no-op
        if self.remoteBranchName == self.repo.branches.local[self.localBranchName].upstream:
            self.cancel()

    def execute(self):
        porcelain.editTrackingBranch(self.repo, self.localBranchName, self.remoteBranchName)

    def refreshWhat(self):
        return TaskAffectsWhat.LOCALREFS
