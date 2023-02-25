from gitfourchette import porcelain
from gitfourchette import util
from gitfourchette.qt import *
from gitfourchette.tasks.repotask import RepoTask, TaskAffectsWhat
from gitfourchette.widgets.brandeddialog import convertToBrandedDialog
from gitfourchette.widgets.commitdialog import CommitDialog
from gitfourchette.widgets.ui_checkoutcommitdialog import Ui_CheckoutCommitDialog
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
                text=util.paragraphs(
                    self.tr("No files are staged for commit."),
                    self.tr("Do you want to create an empty commit anyway?")))

        sig = self.repo.default_signature
        initialMessage = self.getDraftMessage()

        cd = CommitDialog(
            initialText=initialMessage,
            authorSignature=sig,
            committerSignature=sig,
            isAmend=False,
            detachedHead=self.repo.head_is_detached,
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
        if self.message != initialMessage:
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
            detachedHead=self.repo.head_is_detached,
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
        return translate("Operation", "Check out commit")

    def refreshWhat(self):
        return TaskAffectsWhat.INDEX | TaskAffectsWhat.LOCALREFS | TaskAffectsWhat.HEAD

    def flow(self, oid: pygit2.Oid):
        refs = porcelain.refsPointingAtCommit(self.repo, oid)
        refs = [r.removeprefix(porcelain.HEADS_PREFIX) for r in refs if r.startswith(porcelain.HEADS_PREFIX)]

        commitMessage = porcelain.getCommitMessage(self.repo, oid)
        commitMessage, junk = util.messageSummary(commitMessage)

        dlg = QDialog(self.parent())

        ui = Ui_CheckoutCommitDialog()
        ui.setupUi(dlg)
        if refs:
            ui.switchToLocalBranchComboBox.addItems(refs)
            ui.switchToLocalBranchRadioButton.setChecked(True)
        else:
            ui.detachedHeadRadioButton.setChecked(True)
            ui.switchToLocalBranchComboBox.setVisible(False)
            ui.switchToLocalBranchRadioButton.setVisible(False)

        dlg.setWindowTitle(self.tr("Check out commit {0}").format(util.shortHash(oid)))
        convertToBrandedDialog(dlg, subtitleText=f"“{commitMessage}”")
        dlg.show()
        yield from self._flowDialog(dlg)

        # Make sure to copy user input from dialog UI *before* starting worker thread
        dlg.deleteLater()

        if ui.detachedHeadRadioButton.isChecked():
            yield from self._flowBeginWorkerThread()
            porcelain.checkoutCommit(self.repo, oid)

        elif ui.switchToLocalBranchRadioButton.isChecked():
            branchName = ui.switchToLocalBranchComboBox.currentText()
            yield from self._flowBeginWorkerThread()
            porcelain.checkoutLocalBranch(self.repo, branchName)

        elif ui.createBranchRadioButton.isChecked():
            from gitfourchette.tasks.branchtasks import NewBranchFromCommit
            newBranchTask = NewBranchFromCommit(self.parent())
            newBranchTask.setRepo(self.repo)
            yield from newBranchTask.flow(oid)

        else:
            raise NotImplementedError("Unsupported CheckoutCommitDialog outcome")


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
