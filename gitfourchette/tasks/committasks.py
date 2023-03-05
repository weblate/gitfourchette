from gitfourchette import porcelain
from gitfourchette import util
from gitfourchette.qt import *
from gitfourchette.tasks.repotask import RepoTask, TaskAffectsWhat
from gitfourchette.widgets.brandeddialog import convertToBrandedDialog
from gitfourchette.widgets.commitdialog import CommitDialog
from gitfourchette.widgets.ui_checkoutcommitdialog import Ui_CheckoutCommitDialog
from gitfourchette.widgets.ui_identitydialog import Ui_IdentityDialog
import pygit2


class NewCommit(RepoTask):
    def name(self):
        return translate("Operation", "Commit")

    def refreshWhat(self):
        return TaskAffectsWhat.INDEX | TaskAffectsWhat.LOCALREFS | TaskAffectsWhat.HEAD

    @property
    def rw(self) -> 'RepoWidget':  # hack for now - assume parent is a RepoWidget
        return self.parent()

    def getDraftMessage(self):
        return self.rw.state.getDraftCommitMessage()

    def setDraftMessage(self, newMessage):
        self.rw.state.setDraftCommitMessage(newMessage)

    def flow(self):
        yield from self._flowSubtask(SetUpIdentity, translate("IdentityDialog", "Proceed to Commit"))
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
            amendingCommitHash="",
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
        return TaskAffectsWhat.INDEX | TaskAffectsWhat.LOCALREFS | TaskAffectsWhat.HEAD

    @property
    def rw(self) -> 'RepoWidget':  # hack for now - assume parent is a RepoWidget
        return self.parent()

    def getDraftMessage(self):
        return self.rw.state.getDraftCommitMessage(forAmending=True)

    def setDraftMessage(self, newMessage):
        self.rw.state.setDraftCommitMessage(newMessage, forAmending=True)

    def flow(self):
        yield from self._flowSubtask(SetUpIdentity, translate("IdentityDialog", "Proceed to Amend Commit"))
        headCommit = porcelain.getHeadCommit(self.repo)

        # TODO: Retrieve draft message
        cd = CommitDialog(
            initialText=headCommit.message,
            authorSignature=headCommit.author,
            committerSignature=self.repo.default_signature,
            amendingCommitHash=util.shortHash(headCommit.oid),
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


class SetUpIdentity(RepoTask):
    def name(self):
        return translate("Operation", "Set up identity")

    def refreshWhat(self):
        return TaskAffectsWhat.NOTHING

    @staticmethod
    def validateInput(name: str, email: str):
        """ See libgit2/signature.c """

        def isCrud(c: str):
            return ord(c) <= 32 or c in ".,:;<>\"\\'"

        def extractTrimmed(s: str):
            start = 0
            end = len(s)
            while end > 0 and isCrud(s[end-1]):
                end -= 1
            while start < end and isCrud(s[start]):
                start += 1
            return s[start:end]

        for item in name, email:
            if "<" in item or ">" in item:
                return translate("IdentityDialog", "Angle bracket characters are not allowed.")
            elif not extractTrimmed(item):
                return translate("IdentityDialog", "Please fill out both fields.")

        return ""

    def flow(self, okButtonText=""):
        # Getting the default signature will fail if the user's identity is missing or incorrectly set
        try:
            sig = self.repo.default_signature
            return
        except (KeyError, ValueError):
            pass

        dlg = QDialog(self.parent())

        ui = Ui_IdentityDialog()
        ui.setupUi(dlg)
        dlg.ui = ui  # for easier access in unit testing

        util.installLineEditCustomValidator(
            lineEdits=[ui.nameEdit, ui.emailEdit],
            validatorFunc=SetUpIdentity.validateInput,
            errorLabel=ui.validatorLabel,
            gatedWidgets=[ui.buttonBox.button(QDialogButtonBox.Ok)])

        if okButtonText:
            ui.buttonBox.button(QDialogButtonBox.Ok).setText(okButtonText)

        subtitle = translate(
            "IdentityDialog",
            "Before you start creating commits, please set up your identity for Git. "
            "This information will be baked into every commit that you author.")
        convertToBrandedDialog(dlg, subtitleText=subtitle, multilineSubtitle=True)

        util.setWindowModal(dlg)
        dlg.show()
        yield from self._flowDialog(dlg)

        name = ui.nameEdit.text()
        email = ui.emailEdit.text()
        setGlobally = ui.setGlobalIdentity.isChecked()
        dlg.deleteLater()

        yield from self._flowBeginWorkerThread()
        if setGlobally:
            configObject = pygit2.config.Config.get_global_config()
        else:
            configObject = self.repo.config
        configObject['user.name'] = name
        configObject['user.email'] = email


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
            from gitfourchette.tasks.branchtasks import SwitchBranch
            yield from self._flowSubtask(SwitchBranch, branchName, False)

        elif ui.createBranchRadioButton.isChecked():
            from gitfourchette.tasks.branchtasks import NewBranchFromCommit
            yield from self._flowSubtask(NewBranchFromCommit, oid)

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


class ExportCommitAsPatch(RepoTask):
    def name(self):
        return translate("Operation", "Export commit as patch file")

    def refreshWhat(self):
        return TaskAffectsWhat.NOTHING

    def flow(self, oid: pygit2.Oid):
        yield from self._flowBeginWorkerThread()

        commit: pygit2.Commit = self.repo[oid].peel(pygit2.Commit)
        summary, _ = util.messageSummary(commit.message, elision="")
        summary = "".join(c for c in summary if c.isalnum() or c in " ._-")
        summary = summary.strip()[:50].strip()

        composed = ""
        diffs = porcelain.loadCommitDiffs(self.repo, oid)

        for d in diffs:
            composed += d.patch
            assert composed.endswith("\n")
        yield from self._flowExitWorkerThread()

        repoName = os.path.basename(os.path.normpath(self.repo.workdir))
        initialName = f"{repoName} {util.shortHash(oid)} - {summary}.patch"

        savePath, _ = util.PersistentFileDialog.getSaveFileName(
            self.parent(), "SaveFile", self.tr("Save commit as patch file"), initialName)
        if not savePath:
            yield from self._flowAbort()

        yield from self._flowBeginWorkerThread()
        with open(savePath, "wb") as f:
            f.write(composed.encode('utf-8'))
