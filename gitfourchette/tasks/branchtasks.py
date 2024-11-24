# -----------------------------------------------------------------------------
# Copyright (C) 2024 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

import logging

from gitfourchette.forms.newbranchdialog import NewBranchDialog
from gitfourchette.forms.resetheaddialog import ResetHeadDialog
from gitfourchette.forms.textinputdialog import TextInputDialog
from gitfourchette.nav import NavLocator
from gitfourchette.porcelain import *
from gitfourchette.qt import *
from gitfourchette.tasks.repotask import AbortTask, RepoTask, TaskPrereqs, TaskEffects
from gitfourchette.toolbox import *

logger = logging.getLogger(__name__)


class SwitchBranch(RepoTask):
    def prereqs(self) -> TaskPrereqs:
        return TaskPrereqs.NoConflicts

    def flow(self, newBranch: str, askForConfirmation: bool = True, recurseSubmodules: bool = False):
        assert not newBranch.startswith(RefPrefix.HEADS)

        branchObj: Branch = self.repo.branches.local[newBranch]

        if branchObj.is_checked_out():
            message = self.tr("Branch {0} is already checked out.").format(bquo(newBranch))
            raise AbortTask(message, 'information')

        if askForConfirmation:
            text = self.tr("Do you want to switch to branch {0}?").format(bquo(newBranch))
            verb = self.tr("Switch")

            recurseCheckbox = None
            anySubmodules = bool(self.repo.listall_submodules_fast())
            anySubmodules &= pygit2_version_at_least("1.15.1", False)  # TODO: Nuke this once we can drop support for old versions of pygit2
            if anySubmodules:
                recurseCheckbox = QCheckBox(self.tr("Recurse into submodules"))
                recurseCheckbox.setChecked(True)

            yield from self.flowConfirm(text=text, verb=verb, checkbox=recurseCheckbox)
            recurseSubmodules = recurseCheckbox is not None and recurseCheckbox.isChecked()

        if self.repoModel.dangerouslyDetachedHead() and branchObj.target != self.repoModel.headCommitId:
            text = paragraphs(
                self.tr("You are in <b>Detached HEAD</b> mode at commit {0}."),
                self.tr("You might lose track of this commit if you carry on switching to {1}."),
            ).format(btag(shortHash(self.repoModel.headCommitId)), hquo(newBranch))
            yield from self.flowConfirm(text=text, icon='warning')

        yield from self.flowEnterWorkerThread()
        self.effects |= TaskEffects.Refs | TaskEffects.Head

        self.repo.checkout_local_branch(newBranch)

        self.postStatus = self.tr("Switched to branch {0}.").format(tquo(newBranch))

        if recurseSubmodules:
            from gitfourchette.tasks import UpdateSubmodulesRecursive
            yield from self.flowEnterUiThread()
            yield from self.flowSubtask(UpdateSubmodulesRecursive)


class RenameBranch(RepoTask):
    def flow(self, oldBranchName: str):
        assert not oldBranchName.startswith(RefPrefix.HEADS)

        forbiddenBranchNames = self.repo.listall_branches(BranchType.LOCAL)
        forbiddenBranchNames.remove(oldBranchName)

        nameTaken = self.tr("This name is already taken by another local branch.")

        dlg = TextInputDialog(
            self.parentWidget(),
            self.tr("Rename local branch"),
            self.tr("Enter new name:"),
            subtitle=self.tr("Current name: {0}").format(oldBranchName))
        dlg.setText(oldBranchName)
        dlg.setValidator(lambda name: nameValidationMessage(name, forbiddenBranchNames, nameTaken))
        dlg.okButton.setText(self.tr("Rename"))

        yield from self.flowDialog(dlg)
        dlg.deleteLater()
        newBranchName = dlg.lineEdit.text()

        # Bail if identical to dodge AlreadyExistsError
        if newBranchName == oldBranchName:
            raise AbortTask()

        yield from self.flowEnterWorkerThread()
        self.effects |= TaskEffects.Refs

        self.repo.rename_local_branch(oldBranchName, newBranchName)

        self.postStatus = self.tr("Branch {0} renamed to {1}.").format(tquo(oldBranchName), tquo(newBranchName))


class RenameBranchFolder(RepoTask):
    def flow(self, oldFolderRefName: str):
        prefix, oldFolderName = RefPrefix.split(oldFolderRefName)
        assert prefix == RefPrefix.HEADS
        assert not oldFolderName.endswith("/")
        oldFolderNameSlash = oldFolderName + "/"

        forbiddenBranches = set()
        folderBranches = []
        for oldBranchName in self.repo.listall_branches(BranchType.LOCAL):
            if oldBranchName.startswith(oldFolderNameSlash):
                folderBranches.append(oldBranchName)
            else:
                forbiddenBranches.add(oldBranchName)

        def transformBranchName(branchName: str, newFolderName: str) -> str:
            assert branchName.startswith(oldFolderName)
            newBranchName = newFolderName + branchName.removeprefix(oldFolderName)
            newBranchName = newBranchName.removeprefix("/")
            return newBranchName

        def validate(newFolderName: str) -> str:
            for oldBranchName in folderBranches:
                newBranchName = transformBranchName(oldBranchName, newFolderName)
                if newBranchName in forbiddenBranches:
                    return self.tr("This name clashes with existing branch {0}."
                                   ).format(tquo(newBranchName))
            # Finally validate the folder name itself as if it were a branch,
            # but don't test against existing refs (which we just did above),
            # and allow an empty name.
            if not newFolderName:
                return ""
            return nameValidationMessage(newFolderName, [])

        subtitle = self.tr("Folder {0} contains %n branches.", "", len(folderBranches)
                           ).format(lquoe(oldFolderName))

        dlg = TextInputDialog(
            self.parentWidget(),
            self.tr("Rename branch folder"),
            self.tr("Enter new name:"),
            subtitle=subtitle)
        dlg.setText(oldFolderName)
        dlg.setValidator(validate)
        dlg.okButton.setText(self.tr("Rename"))
        dlg.lineEdit.setPlaceholderText(self.tr("Leave blank to move the branches to the root folder."))

        yield from self.flowDialog(dlg)
        dlg.deleteLater()

        newFolderName = dlg.lineEdit.text()

        # Bail if identical to dodge AlreadyExistsError
        if newFolderName == oldFolderName:
            raise AbortTask()

        # Perform rename
        yield from self.flowEnterWorkerThread()
        self.effects |= TaskEffects.Refs

        for oldBranchName in folderBranches:
            newBranchName = transformBranchName(oldBranchName, newFolderName)
            self.repo.rename_local_branch(oldBranchName, newBranchName)

        self.postStatus = self.tr("Branch folder {0} renamed to {1}, %n branches affected.", "", len(folderBranches)
                                  ).format(tquo(oldFolderName), tquo(newFolderName))


class DeleteBranch(RepoTask):
    def flow(self, localBranchName: str):
        assert not localBranchName.startswith(RefPrefix.HEADS)

        if localBranchName == self.repo.head_branch_shorthand:
            text = paragraphs(
                self.tr("Cannot delete {0} because it is the current branch.").format(bquo(localBranchName)),
                self.tr("Before you try again, switch to another branch."))
            raise AbortTask(text)

        text = paragraphs(self.tr("Really delete local branch {0}?").format(bquo(localBranchName)),
                          tr("This cannot be undone!"))

        yield from self.flowConfirm(
            text=text,
            verb=self.tr("Delete branch", "Button label"),
            buttonIcon="SP_DialogDiscardButton")

        yield from self.flowEnterWorkerThread()
        target = self.repo.branches[localBranchName].target
        self.effects |= TaskEffects.Refs
        self.repo.delete_local_branch(localBranchName)

        self.postStatus = self.tr("Branch {0} deleted (commit at tip was {1})."
                                  ).format(tquo(localBranchName), tquo(shortHash(target)))


class DeleteBranchFolder(RepoTask):
    def flow(self, folderRefName: str):
        prefix, folderName = RefPrefix.split(folderRefName)
        assert prefix == RefPrefix.HEADS
        assert not folderName.endswith("/")
        folderNameSlash = folderName + "/"

        currentBranch = self.repo.head_branch_shorthand
        if currentBranch.startswith(folderNameSlash):
            text = paragraphs(
                self.tr("Cannot delete folder {0} because it contains the current branch {1}."
                        ).format(bquo(folderName), bquo(currentBranch)),
                self.tr("Before you try again, switch to another branch."))
            raise AbortTask(text)

        folderBranches = [b for b in self.repo.listall_branches(BranchType.LOCAL)
                          if b.startswith(folderNameSlash)]

        text = paragraphs(
            self.tr("Really delete local branch folder {0}?").format(bquo(folderName)),
            self.tr("<b>%n</b> branches will be deleted.", "", len(folderBranches)) + " " + tr("This cannot be undone!"))

        yield from self.flowConfirm(
            self.tr("Delete branch folder"),
            text,
            detailList=folderBranches,
            verb=self.tr("Delete folder", "Button label"),
            buttonIcon="SP_DialogDiscardButton")

        yield from self.flowEnterWorkerThread()
        self.effects |= TaskEffects.Refs

        for b in folderBranches:
            self.repo.delete_local_branch(b)

        self.postStatus = self.tr("%n branches deleted in folder {0}.", "", len(folderBranches)
                                  ).format(tquo(folderName))


class _NewBranchBaseTask(RepoTask):
    TRACK_ANY_UPSTREAM = ".ANY"

    def _internalFlow(self, tip: Oid, localName: str = "", trackUpstream: str = TRACK_ANY_UPSTREAM):
        repo = self.repo

        tipHashText = shortHash(tip)

        # Are we creating a branch at the tip of the current branch?
        if not repo.head_is_unborn and not repo.head_is_detached and repo.head.target == tip:
            # Let user know that's the HEAD
            tipHashText = f"HEAD ({tipHashText})"

            # Default to the current branch's name (if no name given)
            if not localName:
                localName = repo.head.shorthand

        # Collect upstream names and set initial localName (if we haven't been able to set it above).
        refsPointingHere = repo.listall_refs_pointing_at(tip)
        upstreams = []
        for r in refsPointingHere:
            prefix, shorthand = RefPrefix.split(r)
            if prefix == RefPrefix.HEADS:
                if not localName:
                    localName = shorthand
                branch = repo.branches[shorthand]
                if branch.upstream:
                    upstreams.append(branch.upstream.shorthand)
            elif prefix == RefPrefix.REMOTES:
                if not localName:
                    _, localName = split_remote_branch_shorthand(shorthand)
                upstreams.append(shorthand)

        # Start with a unique name so the branch validator doesn't shout at us
        forbiddenBranchNames = repo.listall_branches(BranchType.LOCAL)
        localName = withUniqueSuffix(localName, forbiddenBranchNames)

        # Ensure no duplicate upstreams (stable order since Python 3.7+)
        upstreams = list(dict.fromkeys(upstreams))

        forbiddenBranchNames = repo.listall_branches(BranchType.LOCAL)

        commitMessage = repo.get_commit_message(tip)
        commitMessage, junk = messageSummary(commitMessage)

        dlg = NewBranchDialog(
            initialName=localName,
            target=tipHashText,
            targetSubtitle=commitMessage,
            upstreams=upstreams,
            reservedNames=forbiddenBranchNames,
            allowSwitching=not self.repo.any_conflicts,
            parent=self.parentWidget())

        if not repo.listall_submodules_fast():
            dlg.ui.recurseSubmodulesCheckBox.setChecked(False)
            dlg.ui.recurseSubmodulesCheckBox.setVisible(False)

        if trackUpstream == self.TRACK_ANY_UPSTREAM:
            trackUpstream = ""
        elif trackUpstream:
            i = dlg.ui.upstreamComboBox.findText(trackUpstream)
            found = i >= 0
            if found:
                dlg.ui.upstreamComboBox.setCurrentIndex(i)

        dlg.setWindowModality(Qt.WindowModality.WindowModal)
        dlg.setFixedHeight(dlg.sizeHint().height())
        dlg.show()
        yield from self.flowDialog(dlg)
        dlg.deleteLater()

        localName = dlg.ui.nameEdit.text()
        trackUpstream = ""
        switchTo = dlg.ui.switchToBranchCheckBox.isChecked()
        recurseSubmodules = dlg.ui.recurseSubmodulesCheckBox.isChecked()
        if dlg.ui.upstreamCheckBox.isChecked():
            trackUpstream = dlg.ui.upstreamComboBox.currentText()

        yield from self.flowEnterWorkerThread()

        # Create local branch
        repo.create_branch_from_commit(localName, tip)
        self.effects |= TaskEffects.Refs | TaskEffects.Head
        self.postStatus = self.tr("Branch {0} created on commit {1}."
                                  ).format(tquo(localName), tquo(shortHash(tip)))

        # Optionally make it track a remote branch
        if trackUpstream:
            repo.edit_upstream_branch(localName, trackUpstream)

        # Switch to it last (if user wants to)
        if switchTo:
            if self.repoModel.dangerouslyDetachedHead() and tip != self.repoModel.headCommitId:
                yield from self.flowEnterUiThread()

                # Refresh GraphView underneath dialog
                from gitfourchette.tasks import RefreshRepo
                yield from self.flowSubtask(RefreshRepo)

                text = paragraphs(
                    self.tr("You are in <b>Detached HEAD</b> mode at commit {0}."),
                    self.tr("You might lose track of this commit if you switch to the new branch."),
                ).format(btag(shortHash(self.repoModel.headCommitId)))
                yield from self.flowConfirm(text=text, icon='warning', verb=self.tr("Switch to {0}").format(lquoe(localName)), cancelText=self.tr("Don’t Switch"))

            repo.checkout_local_branch(localName)

            if recurseSubmodules:
                from gitfourchette.tasks.nettasks import UpdateSubmodulesRecursive
                yield from self.flowEnterUiThread()
                yield from self.flowSubtask(UpdateSubmodulesRecursive)


class NewBranchFromHead(_NewBranchBaseTask):
    def prereqs(self):
        return TaskPrereqs.NoUnborn

    def flow(self):
        tip = self.repo.head_commit.id

        # Initialize upstream to the current branch's upstream, if any
        try:
            headBranchName = self.repo.head.shorthand
            branch = self.repo.branches.local[headBranchName]
            upstream = branch.upstream.shorthand if branch.upstream else ""
            yield from self._internalFlow(tip, trackUpstream=upstream)
        except KeyError:  # e.g. detached HEAD
            # Pick any upstream
            yield from self._internalFlow(tip)


class NewBranchFromCommit(_NewBranchBaseTask):
    def flow(self, tip: Oid):
        yield from self._internalFlow(tip)


class NewBranchFromRef(_NewBranchBaseTask):
    def flow(self, refname: str):
        prefix, name = RefPrefix.split(refname)

        if prefix == RefPrefix.HEADS:
            branch = self.repo.branches.local[name]
            upstream = branch.upstream.shorthand if branch.upstream else ""

        elif prefix == RefPrefix.REMOTES:
            branch = self.repo.branches.remote[name]
            upstream = branch.shorthand
            name = name.removeprefix(branch.remote_name + "/")

        else:
            raise NotImplementedError(f"Unsupported prefix for refname '{refname}'")

        yield from self._internalFlow(branch.target, name, trackUpstream=upstream)


class EditUpstreamBranch(RepoTask):
    def flow(self, localBranchName: str, remoteBranchName: str):
        # Bail if no-op
        currentUpstream = self.repo.branches.local[localBranchName].upstream
        currentUpstreamName = "" if not currentUpstream else currentUpstream.branch_name
        if remoteBranchName == currentUpstreamName:
            raise AbortTask()

        yield from self.flowEnterWorkerThread()
        self.effects |= TaskEffects.Refs
        self.repo.edit_upstream_branch(localBranchName, remoteBranchName)

        if remoteBranchName:
            self.postStatus = self.tr("Branch {0} now tracks {1}.").format(tquo(localBranchName), tquo(remoteBranchName))
        else:
            self.postStatus = self.tr("Branch {0} now tracks no upstream.").format(tquo(localBranchName))


class ResetHead(RepoTask):
    def prereqs(self) -> TaskPrereqs:
        return TaskPrereqs.NoUnborn | TaskPrereqs.NoDetached

    def flow(self, onto: Oid):
        branchName = self.repo.head_branch_shorthand
        commitMessage = self.repo.get_commit_message(onto)
        submoduleDict = self.repo.listall_submodules_dict(absolute_paths=True)
        hasSubmodules = bool(submoduleDict)

        dlg = ResetHeadDialog(onto, branchName, commitMessage, hasSubmodules, parent=self.parentWidget())

        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)  # don't leak dialog
        dlg.setWindowModality(Qt.WindowModality.WindowModal)
        dlg.resize(600, 128)
        yield from self.flowDialog(dlg)
        resetMode = dlg.activeMode
        recurseSubmodules = dlg.recurseSubmodules()

        yield from self.flowEnterWorkerThread()
        self.effects |= TaskEffects.Refs | TaskEffects.Workdir

        self.repo.reset(onto, resetMode)

        if hasSubmodules and recurseSubmodules:
            for submodule in self.repo.recurse_submodules():
                subOnto = submodule.head_id
                logger.info(f"Reset {repr(resetMode)}: Submodule '{submodule.name}' --> {shortHash(subOnto)}")
                with RepoContext(submodule.open()) as subRepo:
                    subRepo.reset(subOnto, resetMode)


class FastForwardBranch(RepoTask):
    def flow(self, localBranchName: str = ""):
        if not localBranchName:
            self.checkPrereqs(TaskPrereqs.NoUnborn | TaskPrereqs.NoDetached)
            localBranchName = self.repo.head_branch_shorthand

        branch = self.repo.branches.local[localBranchName]
        upstream: Branch = branch.upstream
        if not upstream:
            raise AbortTask(self.tr("Can’t fast-forward {0} because it isn’t tracking an upstream branch."
                                    ).format(bquo(branch.shorthand)))

        remoteBranchName = upstream.shorthand

        yield from self.flowEnterWorkerThread()
        self.effects |= TaskEffects.Refs | TaskEffects.Head

        upToDate = self.repo.fast_forward_branch(localBranchName, remoteBranchName)

        ahead = False
        if upToDate:
            ahead = upstream.target != branch.target

        self.jumpTo = NavLocator.inRef(RefPrefix.HEADS + localBranchName)

        yield from self.flowEnterUiThread()

        if upToDate:
            message = [self.tr("No fast-forwarding necessary.")]
            if ahead:
                message.append(self.tr("Your local branch {0} is ahead of {1}."))
            else:
                message.append(self.tr("Your local branch {0} is already up-to-date with {1}."))
            message = paragraphs(message).format(bquo(localBranchName), bquo(remoteBranchName))
            self.postStatus = stripHtml(message)
            yield from self.flowConfirm(text=message, canCancel=False, dontShowAgainKey="NoFastForwardingNecessary")

    def onError(self, exc):
        if isinstance(exc, DivergentBranchesError):
            parentWidget = self.parentWidget()

            lb = exc.local_branch
            rb = exc.remote_branch
            text = paragraphs(
                self.tr("Can’t fast-forward {0} to {1}."),
                self.tr("The branches are divergent."),
            ).format(bquo(lb.shorthand), bquo(rb.shorthand))
            qmb = showWarning(parentWidget, self.name(), text)

            # If it's the checked-out branch, suggest merging
            if lb.is_checked_out():
                mergeCaption = self.tr("Merge into {0}").format(lquoe(lb.shorthand))
                mergeButton = qmb.addButton(mergeCaption, QMessageBox.ButtonRole.ActionRole)
                mergeButton.clicked.connect(lambda: MergeBranch.invoke(parentWidget, rb.name))
        else:
            super().onError(exc)


class MergeBranch(RepoTask):
    def flow(self, them: str):
        assert them.startswith('refs/')

        theirBranch, theirBranchIsLocal = self.repo.get_branch_from_refname(them)
        assert isinstance(theirBranch, Branch)
        _, theirShorthand = RefPrefix.split(them)

        # Run merge analysis on background thread
        yield from self.flowEnterWorkerThread()
        self.repo.refresh_index()
        anyStagedFiles = self.repo.any_staged_changes
        anyConflicts = self.repo.any_conflicts
        myShorthand = self.repo.head_branch_shorthand
        target: Oid = theirBranch.target
        analysis, pref = self.repo.merge_analysis(target)

        yield from self.flowEnterUiThread()
        logger.info(f"Merge analysis: {repr(analysis)} {repr(pref)}")

        if anyConflicts:
            message = paragraphs(
                self.tr("Merging is not possible right now because you have unresolved conflicts."),
                self.tr("Fix the conflicts to proceed."))
            raise AbortTask(message)

        elif anyStagedFiles:
            message = paragraphs(
                self.tr("Merging is not possible right now because you have staged changes."),
                self.tr("Commit your changes or stash them to proceed."))
            raise AbortTask(message)

        elif analysis == MergeAnalysis.UP_TO_DATE:
            message = paragraphs(
                self.tr("No merge is necessary."),
                self.tr("Your branch {0} is already up-to-date with {1}."),
            ).format(bquo(myShorthand), bquo(theirShorthand))
            raise AbortTask(message, icon="information")

        elif analysis == MergeAnalysis.UNBORN:
            message = self.tr("Cannot merge into an unborn head.")
            raise AbortTask(message)

        elif analysis == MergeAnalysis.FASTFORWARD | MergeAnalysis.NORMAL:
            title = self.tr("Fast-forwarding possible")
            message = self.tr("Your branch {0} can simply be fast-forwarded to {1}."
                              ).format(bquo(myShorthand), bquo(theirShorthand))
            hint = paragraphs(
                self.tr("<b>Fast-forwarding</b> means that the tip of your branch will be moved to a more "
                        "recent commit in a linear path, without the need to create a merge commit."),
                self.tr("In this case, {0} will be fast-forwarded to {1}."),
            ).format(bquo(myShorthand), bquo(shortHash(target)))
            yield from self.flowConfirm(title=title, text=message, verb=self.tr("Fast-Forward"),
                                        helpText=hint, dontShowAgainKey="MergeCanFF")
            yield from self.flowEnterWorkerThread()
            self.effects |= TaskEffects.Refs
            self.repo.fast_forward_branch(myShorthand, theirBranch.name)

        elif analysis == MergeAnalysis.NORMAL:
            title = self.tr("Merging may cause conflicts")
            message = paragraphs(
                self.tr("Merging {0} into {1} may cause conflicts.").format(bquo(theirShorthand), bquo(myShorthand)),
                self.tr("You will need to fix the conflicts, if any. Then, commit the result to conclude the merge."))
            yield from self.flowConfirm(title=title, text=message, verb=self.tr("Merge"),
                                        dontShowAgainKey="MergeMayCauseConflicts")

            yield from self.flowEnterWorkerThread()
            self.effects |= TaskEffects.Refs | TaskEffects.Workdir
            self.jumpTo = NavLocator.inWorkdir()

            self.repo.merge(target)

        else:
            raise NotImplementedError(f"Unsupported MergeAnalysis! ma={repr(analysis)} mp={repr(pref)}")


class RecallCommit(RepoTask):
    def flow(self):
        dlg = TextInputDialog(
            self.parentWidget(),
            self.tr("Recall lost commit"),
            self.tr("If you know the hash of a commit that isn’t part of any branches anymore, "
                    "{app} will try to recall it for you.").format(app=qAppName()))
        dlg.okButton.setText(self.tr("Recall"))

        yield from self.flowDialog(dlg)
        dlg.deleteLater()
        needle = dlg.lineEdit.text()

        yield from self.flowEnterWorkerThread()
        self.effects |= TaskEffects.Refs
        obj = self.repo[needle]
        commit: Commit = obj.peel(Commit)
        branchName = f"recall-{shortHash(commit.id)}"
        branchName = withUniqueSuffix(branchName, self.repo.listall_branches())
        self.repo.create_branch_from_commit(branchName, commit.id)
        self.jumpTo = NavLocator.inCommit(commit.id)
