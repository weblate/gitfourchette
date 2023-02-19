from gitfourchette import porcelain
from gitfourchette.qt import *
from gitfourchette.tasks.repotask import RepoTask, TaskAffectsWhat, AbortIfDialogRejected, ReenterWhenDialogFinished
from gitfourchette import util
from gitfourchette.widgets.commitdialog import CommitDialog
from html import escape
import os
import pygit2


class NewCommit(RepoTask):
    def __init__(self, rw):
        super().__init__(rw)
        self.message = None
        self.author = None
        self.committer = None

    def name(self):
        return translate("Operation", "Commit")

    def getDraftMessage(self):
        return self.rw.state.getDraftCommitMessage()

    def setDraftMessage(self, newMessage):
        self.rw.state.setDraftCommitMessage(newMessage)

    def preExecuteUiFlow(self):
        if not porcelain.hasAnyStagedChanges(self.repo):
            yield self.abortIfQuestionRejected(
                title=self.tr("Create empty commit"),
                text=self.tr("No files are staged for commit.<br>Do you want to create an empty commit anyway?"))

        sig = self.repo.default_signature

        cd = CommitDialog(
            initialText=self.getDraftMessage(),
            authorSignature=sig,
            committerSignature=sig,
            isAmend=False,
            parent=self.parent())

        util.setWindowModal(cd)
        cd.show()

        # Reenter task even if dialog rejected, because we want to save the commit message as a draft
        yield ReenterWhenDialogFinished(cd)
        cd.deleteLater()

        self.message = cd.getFullMessage()
        self.author = cd.getOverriddenAuthorSignature()
        self.committer = cd.getOverriddenCommitterSignature()

        # Save commit message as draft now, so we don't lose it if the commit operation fails or is rejected.
        self.setDraftMessage(self.message)

        if cd.result() == QDialog.DialogCode.Rejected:
            self.cancel()

    def execute(self):
        porcelain.createCommit(self.repo, self.message, self.author, self.committer)

    def postExecute(self, success: bool):
        if success:
            self.setDraftMessage(None)  # Clear draft message

    def refreshWhat(self):
        return TaskAffectsWhat.INDEX | TaskAffectsWhat.LOCALREFS


class AmendCommit(RepoTask):
    def __init__(self, rw):
        super().__init__(rw)
        self.message = None
        self.author = None
        self.committer = None

    def name(self):
        return translate("Operation", "Amend commit")

    def getDraftMessage(self):
        return self.rw.state.getDraftCommitMessage(forAmending=True)

    def setDraftMessage(self, newMessage):
        self.rw.state.setDraftCommitMessage(newMessage, forAmending=True)

    def preExecuteUiFlow(self):
        headCommit = porcelain.getHeadCommit(self.repo)

        # TODO: Retrieve draft message
        cd = CommitDialog(
            initialText=headCommit.message,
            authorSignature=headCommit.author,
            committerSignature=self.repo.default_signature,
            isAmend=True,
            parent=self.parent())

        util.setWindowModal(cd)
        cd.show()

        # Reenter task even if dialog rejected, because we want to save the commit message as a draft
        yield ReenterWhenDialogFinished(cd)
        cd.deleteLater()

        self.message = cd.getFullMessage()
        self.author = cd.getOverriddenAuthorSignature()
        self.committer = cd.getOverriddenCommitterSignature()

        # Save amend message as draft now, so we don't lose it if the commit operation fails or is rejected.
        self.setDraftMessage(self.message)

        if cd.result() == QDialog.DialogCode.Rejected:
            self.cancel()

    def execute(self):
        porcelain.amendCommit(self.repo, self.message, self.author, self.committer)

    def postExecute(self, success):
        if success:
            self.setDraftMessage(None)  # Clear draft message

    def refreshWhat(self):
        return TaskAffectsWhat.INDEX | TaskAffectsWhat.LOCALREFS


class CheckoutCommit(RepoTask):
    def __init__(self, rw, oid: pygit2.Oid):
        super().__init__(rw)
        self.oid = oid

    def name(self):
        return translate("Operation", "Checkout commit")

    def execute(self):
        porcelain.checkoutCommit(self.repo, self.oid)

    def refreshWhat(self):
        return TaskAffectsWhat.INDEX | TaskAffectsWhat.LOCALREFS | TaskAffectsWhat.HEAD


class RevertCommit(RepoTask):
    def __init__(self, rw, oid: pygit2.Oid):
        super().__init__(rw)
        self.oid = oid

    def name(self):
        return translate("Operation", "Revert commit")

    def execute(self):
        porcelain.revertCommit(self.repo, self.oid)

    def refreshWhat(self):
        return TaskAffectsWhat.INDEX


class ResetHead(RepoTask):
    def __init__(self, rw, onto: pygit2.Oid, resetMode: str, recurseSubmodules: bool):
        super().__init__(rw)
        self.onto = onto
        self.resetMode = resetMode
        self.recurseSubmodules = recurseSubmodules

    def name(self):
        return translate("Operation", "Reset HEAD ({1})", self.resetMode)

    def execute(self):
        porcelain.resetHead(self.repo, self.onto, self.resetMode, self.recurseSubmodules)

    def refreshWhat(self):
        return TaskAffectsWhat.INDEX | TaskAffectsWhat.LOCALREFS | TaskAffectsWhat.HEAD
