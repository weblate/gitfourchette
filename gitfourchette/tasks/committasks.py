from gitfourchette import porcelain
from gitfourchette.nav import NavLocator
from gitfourchette.qt import *
from gitfourchette.tasks.jumptasks import RefreshRepo
from gitfourchette.tasks.repotask import RepoTask, TaskEffects
from gitfourchette.toolbox import *
from gitfourchette.forms.brandeddialog import convertToBrandedDialog, showTextInputDialog
from gitfourchette.forms.commitdialog import CommitDialog
from gitfourchette.forms.signatureform import SignatureForm
from gitfourchette.forms.ui_checkoutcommitdialog import Ui_CheckoutCommitDialog
from gitfourchette.forms.ui_identitydialog1 import Ui_IdentityDialog1
from gitfourchette.forms.ui_identitydialog2 import Ui_IdentityDialog2
import contextlib
import html
import pygit2


class NewCommit(RepoTask):
    def name(self):
        return translate("Operation", "Commit")

    def effects(self):
        return TaskEffects.Workdir | TaskEffects.Refs | TaskEffects.Head

    @property
    def rw(self) -> 'RepoWidget':  # hack for now - assume parent is a RepoWidget
        return self.parentWidget()

    def flow(self):
        if self.repo.index.conflicts:
            yield from self._flowAbort(
                self.tr("Please fix merge conflicts in the working directory before committing."))

        yield from self._flowSubtask(SetUpIdentityFirstRun, translate("IdentityDialog", "Proceed to Commit"))
        if not porcelain.hasAnyStagedChanges(self.repo):
            yield from self._flowConfirm(
                title=self.tr("Create empty commit"),
                text=paragraphs(
                    self.tr("No files are staged for commit."),
                    self.tr("Do you want to create an empty commit anyway?")))

        sig = self.repo.default_signature
        initialMessage = self.rw.state.getDraftCommitMessage()
        initialAuthor = self.rw.state.getDraftCommitAuthor()

        cd = CommitDialog(
            initialText=initialMessage,
            authorSignature=initialAuthor or sig,
            committerSignature=sig,
            amendingCommitHash="",
            detachedHead=self.repo.head_is_detached,
            parent=self.parentWidget())

        cd.ui.revealAuthor.setChecked(initialAuthor is not None and initialAuthor != sig)

        setWindowModal(cd)

        # Reenter task even if dialog rejected, because we want to save the commit message as a draft
        yield from self._flowDialog(cd, abortTaskIfRejected=False)

        message = cd.getFullMessage()
        author = cd.getOverriddenAuthorSignature()
        committer = cd.getOverriddenCommitterSignature()

        # Save commit message as draft now, so we don't lose it if the commit operation fails or is rejected.
        if message != initialMessage or author != initialAuthor:
            savedAuthor = author if author != sig else None
            self.rw.state.setDraftCommitMessage(message, savedAuthor)

        if cd.result() == QDialog.DialogCode.Rejected:
            cd.deleteLater()
            yield from self._flowAbort()

        cd.deleteLater()

        yield from self._flowBeginWorkerThread()

        if not author:
            author = sig

        porcelain.createCommit(self.repo, message, author, committer)

        yield from self._flowExitWorkerThread()
        self.rw.state.setDraftCommitMessage(None, None)  # Clear draft message


class AmendCommit(RepoTask):
    def name(self):
        return translate("Operation", "Amend commit")

    def effects(self):
        return TaskEffects.Workdir | TaskEffects.Refs | TaskEffects.Head

    @property
    def rw(self) -> 'RepoWidget':  # hack for now - assume parent is a RepoWidget
        return self.parentWidget()

    def getDraftMessage(self):
        return self.rw.state.getDraftCommitMessage(forAmending=True)

    def setDraftMessage(self, newMessage):
        self.rw.state.setDraftCommitMessage(newMessage, forAmending=True)

    def flow(self):
        if self.repo.index.conflicts:
            yield from self._flowAbort(
                self.tr("Please fix merge conflicts in the working directory before amending the commit."))

        yield from self._flowSubtask(SetUpIdentityFirstRun, translate("IdentityDialog", "Proceed to Amend Commit"))
        headCommit = porcelain.getHeadCommit(self.repo)

        # TODO: Retrieve draft message
        cd = CommitDialog(
            initialText=headCommit.message,
            authorSignature=headCommit.author,
            committerSignature=self.repo.default_signature,
            amendingCommitHash=shortHash(headCommit.oid),
            detachedHead=self.repo.head_is_detached,
            parent=self.parentWidget())

        setWindowModal(cd)

        # Reenter task even if dialog rejected, because we want to save the commit message as a draft
        yield from self._flowDialog(cd, abortTaskIfRejected=False)
        cd.deleteLater()

        message = cd.getFullMessage()

        # Save amend message as draft now, so we don't lose it if the commit operation fails or is rejected.
        self.setDraftMessage(message)

        if cd.result() == QDialog.DialogCode.Rejected:
            cd.deleteLater()
            yield from self._flowAbort()

        author = cd.getOverriddenAuthorSignature()
        committer = cd.getOverriddenCommitterSignature()
        cd.deleteLater()

        yield from self._flowBeginWorkerThread()
        porcelain.amendCommit(self.repo, message, author, committer)

        yield from self._flowExitWorkerThread()
        self.setDraftMessage(None)  # Clear draft message


class SetUpIdentityFirstRun(RepoTask):
    def name(self):
        return translate("Operation", "Set up identity")

    def effects(self):
        return TaskEffects.Nothing

    def flow(self, okButtonText=""):
        # Getting the default signature will fail if the user's identity is missing or incorrectly set
        with contextlib.suppress(KeyError, ValueError):
            sig = self.repo.default_signature
            return

        dlg = QDialog(self.parentWidget())

        ui = Ui_IdentityDialog1()
        ui.setupUi(dlg)
        dlg.ui = ui  # for easier access in unit testing

        # Initialize with global identity values (if any)
        initialName, initialEmail = porcelain.getGlobalIdentity()
        ui.nameEdit.setText(initialName)
        ui.emailEdit.setText(initialEmail)

        validator = ValidatorMultiplexer(dlg)
        validator.setGatedWidgets(ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok))
        validator.connectInput(ui.nameEdit, SignatureForm.validateInput)
        validator.connectInput(ui.emailEdit, SignatureForm.validateInput)
        validator.run()

        if okButtonText:
            ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok).setText(okButtonText)

        subtitle = translate(
            "IdentityDialog1",
            "Before editing this repository, please set up your identity for Git. "
            "This information will be embedded into the commits and tags that you author.")

        tweakWidgetFont(dlg.ui.help1, 90)
        tweakWidgetFont(dlg.ui.help2, 90)

        convertToBrandedDialog(dlg, subtitleText=subtitle, multilineSubtitle=True)

        setWindowModal(dlg)
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


class SetUpRepoIdentity(RepoTask):
    def name(self):
        return translate("Operation", "Set up identity")

    def effects(self):
        return TaskEffects.Nothing

    def flow(self):
        repoName = porcelain.repoName(self.repo)

        localName, localEmail = porcelain.getLocalIdentity(self.repo)
        useLocalIdentity = bool(localName or localEmail)

        dlg = QDialog(self.parentWidget())

        ui = Ui_IdentityDialog2()
        ui.setupUi(dlg)
        dlg.ui = ui  # for easier access in unit testing

        ui.localIdentityCheckBox.setText(ui.localIdentityCheckBox.text().format(html.escape(repoName)))
        ui.localIdentityCheckBox.setChecked(useLocalIdentity)

        def onLocalIdentityCheckBoxChanged(newState):
            if newState:
                try:
                    sig: pygit2.Signature = self.repo.default_signature
                    initialName = sig.name
                    initialEmail = sig.email
                except (KeyError, ValueError):
                    initialName = ""
                    initialEmail = ""

                ui.nameEdit.setPlaceholderText("")
                ui.emailEdit.setPlaceholderText("")

                groupBoxTitle = translate("IdentityDialog2", "Custom identity for “{0}”").format(html.escape(repoName))
                okButtonText = translate("IdentityDialog2", "Set custom identity")
            else:
                initialName, initialEmail = porcelain.getGlobalIdentity()

                groupBoxTitle = translate("IdentityDialog2", "Global identity (for “{0}” and other repos)").format(html.escape(repoName))
                okButtonText = translate("IdentityDialog2", "Set global identity")

            ui.nameEdit.setText(initialName)
            ui.emailEdit.setText(initialEmail)
            ui.identityGroupBox.setTitle(groupBoxTitle)
            ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok).setText(okButtonText)
            validator.run()

        ui.localIdentityCheckBox.stateChanged.connect(onLocalIdentityCheckBoxChanged)

        validator = ValidatorMultiplexer(dlg)
        validator.setGatedWidgets(ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok))
        validator.connectInput(ui.nameEdit, SignatureForm.validateInput)
        validator.connectInput(ui.emailEdit, SignatureForm.validateInput)

        onLocalIdentityCheckBoxChanged(useLocalIdentity)

        convertToBrandedDialog(dlg)
        setWindowModal(dlg)
        yield from self._flowDialog(dlg)

        name = ui.nameEdit.text()
        email = ui.emailEdit.text()
        setGlobally = not ui.localIdentityCheckBox.isChecked()
        dlg.deleteLater()

        yield from self._flowBeginWorkerThread()

        if setGlobally:
            try:
                configObject = pygit2.Config.get_global_config()
            except OSError:
                # Last resort, create file
                # TODO: pygit2 should expose git_config_global or git_config_open_global to python code
                configObject = pygit2.Config(os.path.expanduser("~/.gitconfig"))

            # Nuke repo-specific identity
            with contextlib.suppress(KeyError):
                del self.repo.config["user.name"]
            with contextlib.suppress(KeyError):
                del self.repo.config["user.email"]
        else:
            configObject = self.repo.config

        configObject["user.name"] = name
        configObject["user.email"] = email


class CheckoutCommit(RepoTask):
    def name(self):
        return translate("Operation", "Check out commit")

    def effects(self):
        return TaskEffects.Refs | TaskEffects.Head

    def flow(self, oid: pygit2.Oid):
        refs = porcelain.refsPointingAtCommit(self.repo, oid)
        refs = [r.removeprefix(porcelain.HEADS_PREFIX) for r in refs if r.startswith(porcelain.HEADS_PREFIX)]

        commitMessage = porcelain.getCommitMessage(self.repo, oid)
        commitMessage, junk = messageSummary(commitMessage)

        dlg = QDialog(self.parentWidget())

        ui = Ui_CheckoutCommitDialog()
        ui.setupUi(dlg)
        if refs:
            ui.switchToLocalBranchComboBox.addItems(refs)
            ui.switchToLocalBranchRadioButton.setChecked(True)
        else:
            ui.detachedHeadRadioButton.setChecked(True)
            ui.switchToLocalBranchComboBox.setVisible(False)
            ui.switchToLocalBranchRadioButton.setVisible(False)

        dlg.setWindowTitle(self.tr("Check out commit {0}").format(shortHash(oid)))
        convertToBrandedDialog(dlg, subtitleText=f"“{commitMessage}”")
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

    def effects(self):
        return TaskEffects.Workdir | TaskEffects.ShowWorkdir

    def flow(self, oid: pygit2.Oid):
        yield from self._flowBeginWorkerThread()
        porcelain.revertCommit(self.repo, oid)


class ResetHead(RepoTask):
    def name(self):
        return translate("Operation", "Reset HEAD")

    def effects(self):
        return TaskEffects.Workdir | TaskEffects.Refs | TaskEffects.Head

    def flow(self, onto: pygit2.Oid, resetMode: str, recurseSubmodules: bool):
        yield from self._flowBeginWorkerThread()
        porcelain.resetHead(self.repo, onto, resetMode, recurseSubmodules)


class NewTag(RepoTask):
    def name(self):
        return translate("Operation", "New tag")

    def effects(self):
        return TaskEffects.Refs

    def flow(self, oid: pygit2.Oid = None):
        yield from self._flowSubtask(SetUpIdentityFirstRun, translate("IdentityDialog", "Proceed to New Tag"))

        if not oid:
            oid = porcelain.getHeadCommitOid(self.repo)

        dlg = showTextInputDialog(
            self.parentWidget(),
            self.tr("New tag on commit “{0}”").format(shortHash(oid)),
            self.tr("Enter tag name:"),
            okButtonText=self.tr("Create Tag"),
            deleteOnClose=False)
        yield from self._flowDialog(dlg)

        dlg.deleteLater()
        tagName = dlg.lineEdit.text()

        yield from self._flowBeginWorkerThread()
        self.repo.create_tag(
            tagName,
            oid,
            pygit2.GIT_OBJ_COMMIT,
            self.repo.default_signature,
            "empty tag message")


class DeleteTag(RepoTask):
    def name(self):
        return translate("Operation", "Delete tag")

    def effects(self):
        return TaskEffects.Refs

    def flow(self, tagName: str):
        # TODO: This won't delete the tag on remotes

        yield from self._flowConfirm(
            text=self.tr("Really delete tag <b>“{0}”</b>?").format(tagName),
            verb=self.tr("Delete tag"),
            buttonIcon=QStyle.StandardPixmap.SP_DialogDiscardButton)

        yield from self._flowBeginWorkerThread()

        # Stay on this commit after the operation
        tagTarget = porcelain.getCommitOidFromTagName(self.repo, tagName)
        if tagTarget:
            self.jumpTo = NavLocator.inCommit(tagTarget)

        porcelain.deleteTag(self.repo, tagName)


class CherrypickCommit(RepoTask):
    def name(self):
        return translate("Operation", "Cherry-pick")

    def effects(self):
        effects = TaskEffects.Workdir | TaskEffects.ShowWorkdir
        if self.didCommit:
            effects |= TaskEffects.Refs | TaskEffects.Head
        return effects

    @property
    def rw(self) -> 'RepoWidget':  # hack for now - assume parent is a RepoWidget
        return self.parentWidget()

    def flow(self, oid: pygit2.Oid):
        self.didCommit = False

        yield from self._flowBeginWorkerThread()
        porcelain.cherrypick(self.repo, oid)
        anyConflicts = bool(self.repo.index.conflicts)
        commit = self.repo[oid].peel(pygit2.Commit)

        self.repo.state_cleanup()  # also cleans up .git/MERGE_MSG

        yield from self._flowExitWorkerThread()

        if not anyConflicts and not porcelain.hasAnyStagedChanges(self.repo):
            info = self.tr("There’s nothing to cherry-pick from “{0}” "
                           "that the current branch doesn’t already have.").format(shortHash(oid))
            yield from self._flowAbort(info, "information")

        self.rw.state.setDraftCommitMessage(commit.message, author=commit.author)

        if not anyConflicts:
            yield from self._flowSubtask(RefreshRepo, TaskEffects.Workdir | TaskEffects.ShowWorkdir, NavLocator.inStaged(""))
            yield from self._flowConfirm(
                text=self.tr("Cherry-picking “{0}” was successful. "
                             "Do you want to commit the result now?").format(shortHash(oid)),
                verb=self.tr("Commit"),
                cancelText=self.tr("Review changes"))
            yield from self._flowSubtask(NewCommit)
            self.didCommit = True
