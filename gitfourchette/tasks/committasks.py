import logging
from contextlib import suppress

from gitfourchette.forms.brandeddialog import convertToBrandedDialog, showTextInputDialog
from gitfourchette.forms.commitdialog import CommitDialog
from gitfourchette.forms.identitydialog import IdentityDialog
from gitfourchette.forms.signatureform import SignatureOverride
from gitfourchette.forms.ui_checkoutcommitdialog import Ui_CheckoutCommitDialog
from gitfourchette.nav import NavLocator
from gitfourchette.porcelain import *
from gitfourchette.qt import *
from gitfourchette.tasks.jumptasks import RefreshRepo
from gitfourchette.tasks.repotask import AbortTask, RepoTask, TaskPrereqs, TaskEffects
from gitfourchette.toolbox import *

logger = logging.getLogger(__name__)


class NewCommit(RepoTask):
    def prereqs(self):
        return TaskPrereqs.NoConflicts

    def effects(self):
        return TaskEffects.Workdir | TaskEffects.Refs | TaskEffects.Head

    def flow(self):
        from gitfourchette.tasks import Jump

        uiPrefs = self.repoModel.prefs

        # Jump to workdir
        yield from self.flowSubtask(Jump, NavLocator.inWorkdir())

        if not self.repo.any_staged_changes:
            yield from self.flowConfirm(
                title=self.tr("Create empty commit"),
                verb=self.tr("Empty commit"),
                text=paragraphs(
                    self.tr("No files are staged for commit."),
                    self.tr("Do you want to create an empty commit anyway?")))

        yield from self.flowSubtask(SetUpGitIdentity, self.tr("Proceed to Commit"))

        fallbackSignature = self.repo.default_signature
        initialMessage = uiPrefs.draftCommitMessage

        cd = CommitDialog(
            initialText=initialMessage,
            authorSignature=fallbackSignature,
            committerSignature=fallbackSignature,
            amendingCommitHash="",
            detachedHead=self.repo.head_is_detached,
            repositoryState=self.repo.state(),
            parent=self.parentWidget())

        if uiPrefs.draftCommitSignatureOverride == SignatureOverride.Nothing:
            cd.ui.revealSignature.setChecked(False)
        else:
            cd.ui.revealSignature.setChecked(True)
            cd.ui.signature.setSignature(uiPrefs.draftCommitSignature)
            cd.ui.signature.ui.replaceComboBox.setCurrentIndex(int(uiPrefs.draftCommitSignatureOverride) - 1)

        cd.setWindowModality(Qt.WindowModality.WindowModal)

        # Reenter task even if dialog rejected, because we want to save the commit message as a draft
        yield from self.flowDialog(cd, abortTaskIfRejected=False)

        message = cd.getFullMessage()
        author = cd.getOverriddenAuthorSignature() or fallbackSignature
        committer = cd.getOverriddenCommitterSignature() or fallbackSignature
        overriddenSignatureKind = cd.getOverriddenSignatureKind()
        signatureIsOverridden = overriddenSignatureKind != SignatureOverride.Nothing

        # Save commit message/signature as draft now,
        # so we don't lose it if the commit operation fails or is rejected.
        if message != initialMessage or signatureIsOverridden:
            uiPrefs.draftCommitMessage = message
            uiPrefs.draftCommitSignature = cd.ui.signature.getSignature() if signatureIsOverridden else None
            uiPrefs.draftCommitSignatureOverride = overriddenSignatureKind
            uiPrefs.setDirty()

        if cd.result() == QDialog.DialogCode.Rejected:
            cd.deleteLater()
            raise AbortTask()

        cd.deleteLater()

        yield from self.flowEnterWorkerThread()
        self.repo.create_commit_on_head(message, author, committer)

        yield from self.flowEnterUiThread()
        uiPrefs.clearDraftCommit()


class AmendCommit(RepoTask):
    def prereqs(self):
        return TaskPrereqs.NoUnborn | TaskPrereqs.NoConflicts | TaskPrereqs.NoCherrypick

    def effects(self):
        return TaskEffects.Workdir | TaskEffects.Refs | TaskEffects.Head

    def getDraftMessage(self):
        return self.repoModel.prefs.draftAmendMessage

    def setDraftMessage(self, newMessage):
        self.repoModel.prefs.draftAmendMessage = newMessage
        self.repoModel.prefs.setDirty()

    def flow(self):
        from gitfourchette.tasks import Jump

        # Jump to workdir
        yield from self.flowSubtask(Jump, NavLocator.inWorkdir())

        yield from self.flowSubtask(SetUpGitIdentity, self.tr("Proceed to Amend Commit"))

        headCommit = self.repo.head_commit
        fallbackSignature = self.repo.default_signature

        # TODO: Retrieve draft message
        cd = CommitDialog(
            initialText=headCommit.message,
            authorSignature=headCommit.author,
            committerSignature=fallbackSignature,
            amendingCommitHash=shortHash(headCommit.id),
            detachedHead=self.repo.head_is_detached,
            repositoryState=self.repo.state(),
            parent=self.parentWidget())

        cd.setWindowModality(Qt.WindowModality.WindowModal)

        # Reenter task even if dialog rejected, because we want to save the commit message as a draft
        yield from self.flowDialog(cd, abortTaskIfRejected=False)
        cd.deleteLater()

        message = cd.getFullMessage()

        # Save amend message as draft now, so we don't lose it if the commit operation fails or is rejected.
        self.setDraftMessage(message)

        if cd.result() == QDialog.DialogCode.Rejected:
            raise AbortTask()

        author = cd.getOverriddenAuthorSignature()  # no "or fallback" here - leave author intact for amending
        committer = cd.getOverriddenCommitterSignature() or fallbackSignature

        yield from self.flowEnterWorkerThread()
        self.repo.amend_commit_on_head(message, author, committer)

        yield from self.flowEnterUiThread()
        self.repoModel.prefs.clearDraftAmend()


class SetUpGitIdentity(RepoTask):
    def effects(self):
        return TaskEffects.Nothing

    def flow(self, okButtonText="", firstRun=True):
        if firstRun:
            # Getting the default signature will fail if the user's identity is missing or incorrectly set
            try:
                _ = self.repo.default_signature
                return
            except (KeyError, ValueError):
                pass

        initialName, initialEmail, editLevel = GitConfigHelper.global_identity()

        # Fall back to a sensible path if the identity comes from /etc/gitconfig or some other systemwide file
        if editLevel not in [GitConfigLevel.XDG, GitConfigLevel.GLOBAL]:
            # Favor XDG path if we can, otherwise use ~/.gitconfig
            if FREEDESKTOP and GitSettings.search_path[GitConfigLevel.XDG]:
                editLevel = GitConfigLevel.XDG
            else:
                editLevel = GitConfigLevel.GLOBAL

        editPath = GitConfigHelper.path_for_level(editLevel, missing_dir_ok=True)

        dlg = IdentityDialog(firstRun, initialName, initialEmail, editPath,
                             self.repo.has_local_identity(), self.parentWidget())

        if okButtonText:
            dlg.ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok).setText(okButtonText)

        dlg.resize(512, 0)
        dlg.setWindowModality(Qt.WindowModality.WindowModal)
        yield from self.flowDialog(dlg)

        name, email = dlg.identity()
        dlg.deleteLater()

        configObject = GitConfigHelper.ensure_file(editLevel)
        configObject['user.name'] = name
        configObject['user.email'] = email

        # An existing repo will automatically pick up the new GLOBAL config file,
        # but apparently not the XDG config file... So add it to be sure.
        with suppress(ValueError):
            self.repo.config.add_file(editPath, editLevel, force=False)


class CheckoutCommit(RepoTask):
    def effects(self):
        return TaskEffects.Refs | TaskEffects.Head

    def flow(self, oid: Oid):
        refs = self.repo.listall_refs_pointing_at(oid)
        refs = [r.removeprefix(RefPrefix.HEADS) for r in refs if r.startswith(RefPrefix.HEADS)]

        commitMessage = self.repo.get_commit_message(oid)
        commitMessage, junk = messageSummary(commitMessage)

        dlg = QDialog(self.parentWidget())

        ui = Ui_CheckoutCommitDialog()
        ui.setupUi(dlg)
        ok = ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok)
        ui.detachedHeadRadioButton.clicked.connect(lambda: ok.setText(self.tr("Detach HEAD")))
        ui.switchToLocalBranchRadioButton.clicked.connect(lambda: ok.setText(self.tr("Switch Branch")))
        ui.createBranchRadioButton.clicked.connect(lambda: ok.setText(self.tr("Create Branch...")))
        if refs:
            ui.switchToLocalBranchComboBox.addItems(refs)
            ui.switchToLocalBranchRadioButton.click()
        else:
            ui.detachedHeadRadioButton.click()
            ui.switchToLocalBranchComboBox.setVisible(False)
            ui.switchToLocalBranchRadioButton.setVisible(False)

        dlg.setWindowTitle(self.tr("Check out commit {0}").format(shortHash(oid)))
        convertToBrandedDialog(dlg, subtitleText=tquo(commitMessage))
        dlg.setWindowModality(Qt.WindowModality.WindowModal)
        yield from self.flowDialog(dlg)

        # Make sure to copy user input from dialog UI *before* starting worker thread
        dlg.deleteLater()

        if ui.detachedHeadRadioButton.isChecked():
            if self.repoModel.dangerouslyDetachedHead() and oid != self.repoModel.headCommitId:
                text = paragraphs(
                    self.tr("You are in <b>Detached HEAD</b> mode at commit {0}."),
                    self.tr("You might lose track of this commit if you carry on checking out another commit ({1})."),
                ).format(btag(shortHash(self.repoModel.headCommitId)), shortHash(oid))
                yield from self.flowConfirm(text=text, icon='warning')

            yield from self.flowEnterWorkerThread()
            self.repo.checkout_commit(oid)

            # Force sidebar to select detached HEAD
            self.jumpTo = NavLocator.inRef("HEAD")

        elif ui.switchToLocalBranchRadioButton.isChecked():
            branchName = ui.switchToLocalBranchComboBox.currentText()
            from gitfourchette.tasks.branchtasks import SwitchBranch
            yield from self.flowSubtask(SwitchBranch, branchName, False)

        elif ui.createBranchRadioButton.isChecked():
            from gitfourchette.tasks.branchtasks import NewBranchFromCommit
            yield from self.flowSubtask(NewBranchFromCommit, oid)

        else:
            raise NotImplementedError("Unsupported CheckoutCommitDialog outcome")


class NewTag(RepoTask):
    def prereqs(self):
        return TaskPrereqs.NoUnborn

    def effects(self):
        return TaskEffects.Refs

    def flow(self, oid: Oid = None, signIt: bool = False):
        if signIt:
            yield from self.flowSubtask(SetUpGitIdentity, self.tr("Proceed to New Tag"))

        if not oid:
            oid = self.repo.head_commit_id

        reservedNames = self.repo.listall_tags()
        nameTaken = self.tr("This name is already taken by another tag.")

        dlg = showTextInputDialog(
            self.parentWidget(),
            self.tr("New tag on commit {0}").format(tquo(shortHash(oid))),
            self.tr("Enter tag name:"),
            okButtonText=self.tr("Create Tag"),
            deleteOnClose=False,
            validate=lambda name: nameValidationMessage(name, reservedNames, nameTaken))
        yield from self.flowDialog(dlg)

        dlg.deleteLater()
        tagName = dlg.lineEdit.text()

        yield from self.flowEnterWorkerThread()

        if signIt:
            self.repo.create_tag(tagName, oid, ObjectType.COMMIT, self.repo.default_signature, "")
        else:
            self.repo.create_reference(RefPrefix.TAGS + tagName, oid)


class DeleteTag(RepoTask):
    def effects(self):
        return TaskEffects.Refs

    def flow(self, tagName: str):
        # TODO: This won't delete the tag on remotes

        assert not tagName.startswith("refs/")

        yield from self.flowConfirm(
            text=self.tr("Really delete tag {0}?").format(bquo(tagName)),
            verb=self.tr("Delete tag"),
            buttonIcon="SP_DialogDiscardButton")

        yield from self.flowEnterWorkerThread()

        # Stay on this commit after the operation
        tagTarget = self.repo.commit_id_from_tag_name(tagName)
        if tagTarget:
            self.jumpTo = NavLocator.inCommit(tagTarget)

        self.repo.delete_tag(tagName)


class RevertCommit(RepoTask):
    def prereqs(self) -> TaskPrereqs:
        return TaskPrereqs.NoConflicts | TaskPrereqs.NoStagedChanges

    def effects(self):
        effects = TaskEffects.Workdir | TaskEffects.ShowWorkdir
        if self.didCommit:
            effects |= TaskEffects.Refs | TaskEffects.Head
        return effects

    def flow(self, oid: Oid):
        self.didCommit = False

        # TODO: Remove this when we can stop supporting pygit2 <= 1.15.0
        pygit2_version_at_least("1.15.1")

        text = paragraphs(
            self.tr("Do you want to revert commit {0}?"),
            self.tr("You will have an opportunity to review the affected files in your working directory."),
        ).format(btag(shortHash(oid)))
        yield from self.flowConfirm(text=text)

        yield from self.flowEnterWorkerThread()
        repoModel = self.repoModel
        repo = self.repo
        commit = repo.peel_commit(oid)
        repo.revert(commit)

        anyConflicts = repo.any_conflicts
        dud = not anyConflicts and not repo.any_staged_changes

        # If reverting didn't do anything, don't let the REVERT state linger.
        # (Otherwise, the state will be cleared when we commit)
        if dud:
            repo.state_cleanup()

        yield from self.flowEnterUiThread()

        if dud:
            info = self.tr("There’s nothing to revert from {0} that the current branch hasn’t already undone."
                           ).format(bquo(shortHash(oid)))
            raise AbortTask(info, "information")

        yield from self.flowEnterUiThread()

        repoModel.prefs.draftCommitMessage = self.repo.message
        repoModel.prefs.setDirty()

        if not anyConflicts:
            yield from self.flowSubtask(RefreshRepo, TaskEffects.Workdir | TaskEffects.ShowWorkdir, NavLocator.inStaged(""))
            text = self.tr("Reverting {0} was successful. Do you want to commit the result now?")
            text = text.format(bquo(shortHash(oid)))
            yield from self.flowConfirm(text=text, verb=self.tr("Commit"), cancelText=self.tr("Review changes"))
            yield from self.flowSubtask(NewCommit)
            self.didCommit = True


class CherrypickCommit(RepoTask):
    def prereqs(self):
        # Prevent cherry-picking with staged changes, like vanilla git (despite libgit2 allowing it)
        return TaskPrereqs.NoConflicts | TaskPrereqs.NoStagedChanges

    def effects(self):
        effects = TaskEffects.Workdir | TaskEffects.ShowWorkdir
        if self.didCommit:
            effects |= TaskEffects.Refs | TaskEffects.Head
        return effects

    def flow(self, oid: Oid):
        self.didCommit = False

        yield from self.flowEnterWorkerThread()
        commit = self.repo.peel_commit(oid)
        self.repo.cherrypick(oid)

        anyConflicts = self.repo.any_conflicts
        dud = not anyConflicts and not self.repo.any_staged_changes

        assert self.repo.state() == RepositoryState.CHERRYPICK

        # If cherrypicking didn't do anything, don't let the CHERRYPICK state linger.
        # (Otherwise, the state will be cleared when we commit)
        if dud:
            self.repo.state_cleanup()

        # Back to UI thread
        yield from self.flowEnterUiThread()

        if dud:
            info = self.tr("There’s nothing to cherry-pick from {0} that the current branch doesn’t already have."
                           ).format(bquo(shortHash(oid)))
            raise AbortTask(info, "information")

        self.repoModel.prefs.draftCommitMessage = self.repo.message
        self.repoModel.prefs.draftCommitSignature = commit.author
        self.repoModel.prefs.draftCommitSignatureOverride = SignatureOverride.Author
        self.repoModel.prefs.setDirty()

        if not anyConflicts:
            yield from self.flowSubtask(RefreshRepo, TaskEffects.Workdir | TaskEffects.ShowWorkdir, NavLocator.inStaged(""))
            yield from self.flowConfirm(
                text=self.tr("Cherry-picking {0} was successful. "
                             "Do you want to commit the result now?").format(bquo(shortHash(oid))),
                verb=self.tr("Commit"),
                cancelText=self.tr("Review changes"))
            yield from self.flowSubtask(NewCommit)
            self.didCommit = True
