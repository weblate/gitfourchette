from gitfourchette import porcelain
from gitfourchette.porcelain import HEADS_PREFIX, REMOTES_PREFIX
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
        assert not self.newBranch.startswith(HEADS_PREFIX)

    def name(self):
        return translate("Operation", "Switch to branch")

    def execute(self):
        porcelain.checkoutLocalBranch(self.repo, self.newBranch)


class RenameBranch(RepoTask):
    def __init__(self, rw, oldBranchName: str):
        super().__init__(rw)
        self.oldBranchName = oldBranchName
        self.newBranchName = oldBranchName
        assert not self.oldBranchName.startswith(HEADS_PREFIX)

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
        assert not localBranchName.startswith(HEADS_PREFIX)

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
        self.tip = None
        self.localName = ""
        self.switchTo = False
        self.upstream = ""

    def name(self):
        return translate("Operation", "New local branch")

    def _initialBranchSettings(self, tip: pygit2.Oid):
        upstreams = []

        # If we're creating a branch at the tip of the current branch, default to its name
        if (not self.localName
                and not self.repo.head_is_unborn
                and not self.repo.head_is_detached
                and self.repo.head.target == tip):
            self.localName = self.repo.head.shorthand

        # Collect upstream names and set initial localName (if we haven't been able to set it above).
        refsPointingHere = porcelain.mapCommitsToReferences(self.repo)[tip]

        for r in refsPointingHere:
            if r.startswith(HEADS_PREFIX):
                branchName = r.removeprefix(HEADS_PREFIX)
                if not self.localName:
                    self.localName = branchName

                branch = self.repo.branches[branchName]
                if branch.upstream and branch.upstream.shorthand not in upstreams:
                    upstreams.append(branch.upstream.shorthand)

            elif r.startswith(REMOTES_PREFIX):
                shorthand = r.removeprefix(REMOTES_PREFIX)
                if not self.localName:
                    _, self.localName = porcelain.splitRemoteBranchShorthand(shorthand)
                if shorthand not in upstreams:
                    upstreams.append(shorthand)

        if self.upstream not in upstreams:
            self.upstream = ""

        return upstreams

    def preExecuteUiFlow(self):
        if not self.tip:
            self.tip = porcelain.getHeadCommit(self.repo).oid

        upstreams = self._initialBranchSettings(self.tip)

        forbiddenBranchNames = [""] + self.repo.listall_branches(pygit2.GIT_BRANCH_LOCAL)

        commitMessage = porcelain.getCommitMessage(self.repo, self.tip)
        commitMessage, junk = util.messageSummary(commitMessage)

        dlg = NewBranchDialog(
            initialName=self.localName,
            target=util.shortHash(self.tip),
            targetSubtitle=commitMessage,
            upstreams=upstreams,
            forbiddenBranchNames=forbiddenBranchNames,
            parent=self.parent())

        if self.upstream:
            i = dlg.ui.upstreamComboBox.findText(self.upstream)
            if i >= 0:
                dlg.ui.upstreamComboBox.setCurrentIndex(i)
                if self.switchTo:
                    dlg.ui.upstreamCheckBox.setChecked(True)

        util.setWindowModal(dlg)
        dlg.show()
        dlg.setMaximumHeight(dlg.height())
        yield AbortIfDialogRejected(dlg)
        dlg.deleteLater()

        self.localName = dlg.ui.nameEdit.text()
        self.upstream = ""
        self.switchTo = dlg.ui.switchToBranchCheckBox.isChecked()
        if dlg.ui.upstreamCheckBox.isChecked():
            self.upstream = dlg.ui.upstreamComboBox.currentText()

    def execute(self):
        # Create local branch
        porcelain.newBranchFromCommit(self.repo, self.localName, self.tip, switchTo=False)

        # Optionally make it track a remote branch
        if self.upstream:
            porcelain.editTrackingBranch(self.repo, self.localName, self.upstream)

        # Switch to it last (if user wants to)
        if self.switchTo:
            porcelain.checkoutLocalBranch(self.repo, self.localName)

    def refreshWhat(self):
        return TaskAffectsWhat.LOCALREFS


class NewBranchFromCommit(NewBranch):
    def __init__(self, rw, tip: pygit2.Oid):
        super().__init__(rw)
        self.tip = tip


class NewBranchFromLocalBranch(NewBranch):
    def __init__(self, rw, localBranchName: str):
        super().__init__(rw)
        assert not localBranchName.startswith(HEADS_PREFIX)
        branch = self.repo.branches.local[localBranchName]
        self.tip = branch.target
        self.localName = localBranchName
        if branch.upstream:
            self.upstream = branch.upstream.shorthand


class NewTrackingBranch(NewBranch):
    def __init__(self, rw, remoteBranchName: str):
        super().__init__(rw)
        assert not remoteBranchName.startswith(REMOTES_PREFIX)
        branch = self.repo.branches.remote[remoteBranchName]
        self.tip = branch.target
        self.localName = remoteBranchName.removeprefix(branch.remote_name + "/")
        self.upstream = branch.shorthand
        self.switchTo = True


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
