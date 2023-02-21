from gitfourchette import porcelain
from gitfourchette import util
from gitfourchette.qt import *
from gitfourchette.tasks.repotask import RepoTask, TaskAffectsWhat
from gitfourchette.widgets.commitdialog import CommitDialog
import pygit2


class NewCommit(RepoTask):
    def name(self):
        return translate("Operation", "Commit")

    def refreshWhat(self):
        return TaskAffectsWhat.INDEX | TaskAffectsWhat.LOCALREFS

    @property
    def rw(self) -> 'RepoWidget':  # hack for now - assume parent is a RepoWidget
        return self.parent()

    def getDraftMessage(self):
        return self.rw.state.getDraftCommitMessage()

    def setDraftMessage(self, newMessage):
        self.rw.state.setDraftCommitMessage(newMessage)

    def flow(self):
        if not porcelain.hasAnyStagedChanges(self.repo):
            yield from self._flowConfirm(
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
        yield from self._flowDialog(cd, abortTaskIfRejected=False)
        cd.deleteLater()

        self.message = cd.getFullMessage()
        self.author = cd.getOverriddenAuthorSignature()
        self.committer = cd.getOverriddenCommitterSignature()

        # Save commit message as draft now, so we don't lose it if the commit operation fails or is rejected.
        self.setDraftMessage(self.message)

        if cd.result() == QDialog.DialogCode.Rejected:
            yield from self._flowAbort()

        yield from self._flowBeginWorkerThread()
        porcelain.createCommit(self.repo, self.message, self.author, self.committer)

        yield from self._flowExitWorkerThread()
        self.setDraftMessage(None)  # Clear draft message


class AmendCommit(RepoTask):
    def name(self):
        return translate("Operation", "Amend commit")

    def refreshWhat(self):
        return TaskAffectsWhat.INDEX | TaskAffectsWhat.LOCALREFS

    @property
    def rw(self) -> 'RepoWidget':  # hack for now - assume parent is a RepoWidget
        return self.parent()

    def getDraftMessage(self):
        return self.rw.state.getDraftCommitMessage(forAmending=True)

    def setDraftMessage(self, newMessage):
        self.rw.state.setDraftCommitMessage(newMessage, forAmending=True)

    def flow(self):
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
        yield from self._flowDialog(cd, abortTaskIfRejected=False)
        cd.deleteLater()

        message = cd.getFullMessage()
        author = cd.getOverriddenAuthorSignature()
        committer = cd.getOverriddenCommitterSignature()

        # Save amend message as draft now, so we don't lose it if the commit operation fails or is rejected.
        self.setDraftMessage(message)

        if cd.result() == QDialog.DialogCode.Rejected:
            yield from self._flowAbort()

        yield from self._flowBeginWorkerThread()
        porcelain.amendCommit(self.repo, message, author, committer)

        yield from self._flowExitWorkerThread()
        self.setDraftMessage(None)  # Clear draft message


class CheckoutCommit(RepoTask):
    def name(self):
        return translate("Operation", "Checkout commit")

    def refreshWhat(self):
        return TaskAffectsWhat.INDEX | TaskAffectsWhat.LOCALREFS | TaskAffectsWhat.HEAD

    def flow(self, oid: pygit2.Oid):
        yield from self._flowBeginWorkerThread()
        porcelain.checkoutCommit(self.repo, oid)


class RevertCommit(RepoTask):
    def name(self):
        return translate("Operation", "Revert commit")

    def refreshWhat(self):
        return TaskAffectsWhat.INDEX

    def flow(self, oid: pygit2.Oid):
        yield from self._flowBeginWorkerThread()
        porcelain.revertCommit(self.repo, oid)


class ResetHead(RepoTask):
    def name(self):
        return translate("Operation", "Reset HEAD")

    def refreshWhat(self):
        return TaskAffectsWhat.INDEX | TaskAffectsWhat.LOCALREFS | TaskAffectsWhat.HEAD

    def flow(self, onto: pygit2.Oid, resetMode: str, recurseSubmodules: bool):
        yield from self._flowBeginWorkerThread()
        porcelain.resetHead(self.repo, onto, resetMode, recurseSubmodules)
