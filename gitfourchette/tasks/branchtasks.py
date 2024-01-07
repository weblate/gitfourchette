import logging

from gitfourchette.porcelain import *
from gitfourchette.qt import *
from gitfourchette.tasks.repotask import RepoTask, TaskEffects
from gitfourchette.toolbox import *
from gitfourchette.forms.brandeddialog import showTextInputDialog
from gitfourchette.forms.newbranchdialog import NewBranchDialog
from gitfourchette.forms.trackedbranchdialog import TrackedBranchDialog

logger = logging.getLogger(__name__)


class SwitchBranch(RepoTask):
    def effects(self):
        return TaskEffects.Refs | TaskEffects.Head

    def flow(self, newBranch: str, askForConfirmation: bool):
        assert not newBranch.startswith(RefPrefix.HEADS)

        if self.repo.branches.local[newBranch].is_checked_out():
            yield from self.flowAbort(
                self.tr("Branch <b>“{0}”</b> is already checked out.").format(escape((newBranch))),
                'information')

        if askForConfirmation:
            text = self.tr("Do you want to switch to branch <b>“{0}”</b>?").format(escape(newBranch))
            verb = self.tr("Switch")
            yield from self.flowConfirm(text=text, verb=verb)

        yield from self.flowEnterWorkerThread()
        self.repo.checkout_local_branch(newBranch)


class RenameBranch(RepoTask):
    def flow(self, oldBranchName: str):
        assert not oldBranchName.startswith(RefPrefix.HEADS)

        forbiddenBranchNames = self.repo.listall_branches(GIT_BRANCH_LOCAL)
        forbiddenBranchNames.remove(oldBranchName)

        nameTaken = self.tr("This name is already taken by another local branch.")

        dlg = showTextInputDialog(
            self.parentWidget(),
            self.tr("Rename local branch “{0}”").format(escape(elide(oldBranchName))),
            self.tr("Enter new name:"),
            oldBranchName,
            okButtonText=self.tr("Rename"),
            validate=lambda name: nameValidationMessage(name, forbiddenBranchNames, nameTaken),
            deleteOnClose=False)

        yield from self.flowDialog(dlg)
        dlg.deleteLater()
        newBranchName = dlg.lineEdit.text()

        yield from self.flowEnterWorkerThread()
        self.repo.rename_local_branch(oldBranchName, newBranchName)

    def effects(self):
        return TaskEffects.Refs


class DeleteBranch(RepoTask):
    def flow(self, localBranchName: str):
        assert not localBranchName.startswith(RefPrefix.HEADS)

        if localBranchName == self.repo.head_branch_shorthand:
            text = paragraphs(
                self.tr("Cannot delete “{0}” because it is the current branch.").format(escape(localBranchName)),
                self.tr("Before you try again, switch to another branch."))
            yield from self.flowAbort(text)

        text = paragraphs(self.tr("Really delete local branch <b>“{0}”</b>?").format(escape(localBranchName)),
                          tr("This cannot be undone!"))

        yield from self.flowConfirm(
            text=text,
            verb=self.tr("Delete branch", "Button label"),
            buttonIcon=QStyle.StandardPixmap.SP_DialogDiscardButton)

        yield from self.flowEnterWorkerThread()
        self.repo.delete_local_branch(localBranchName)

    def effects(self):
        return TaskEffects.Refs


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
        localName = repo.generate_unique_local_branch_name(localName)

        # Ensure no duplicate upstreams (stable order since Python 3.7+)
        upstreams = list(dict.fromkeys(upstreams))

        forbiddenBranchNames = repo.listall_branches(GIT_BRANCH_LOCAL)

        commitMessage = repo.get_commit_message(tip)
        commitMessage, junk = messageSummary(commitMessage)

        dlg = NewBranchDialog(
            initialName=localName,
            target=tipHashText,
            targetSubtitle=commitMessage,
            upstreams=upstreams,
            reservedNames=forbiddenBranchNames,
            parent=self.parentWidget())

        if trackUpstream == self.TRACK_ANY_UPSTREAM:
            trackUpstream = ""
            dlg.ui.upstreamCheckBox.setChecked(bool(upstreams))
        elif trackUpstream:
            i = dlg.ui.upstreamComboBox.findText(trackUpstream)
            found = i >= 0
            dlg.ui.upstreamCheckBox.setChecked(found)
            if found:
                dlg.ui.upstreamComboBox.setCurrentIndex(i)

        setWindowModal(dlg)
        dlg.show()
        dlg.setMaximumHeight(dlg.height())
        yield from self.flowDialog(dlg)
        dlg.deleteLater()

        localName = dlg.ui.nameEdit.text()
        trackUpstream = ""
        switchTo = dlg.ui.switchToBranchCheckBox.isChecked()
        if dlg.ui.upstreamCheckBox.isChecked():
            trackUpstream = dlg.ui.upstreamComboBox.currentText()

        yield from self.flowEnterWorkerThread()

        # Create local branch
        repo.create_branch_from_commit(localName, tip)

        # Optionally make it track a remote branch
        if trackUpstream:
            repo.edit_tracking_branch(localName, trackUpstream)

        # Switch to it last (if user wants to)
        if switchTo:
            repo.checkout_local_branch(localName)

    def effects(self):
        return TaskEffects.Refs


class NewBranchFromHead(_NewBranchBaseTask):
    def flow(self):
        if self.repo.head_is_unborn:
            yield from self.flowAbort(
                self.tr("Cannot create a local branch when HEAD is unborn.")
                + " " + tr("Please create the initial commit in this repository first."))

        tip = self.repo.head_commit.oid

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


class NewBranchFromLocalBranch(_NewBranchBaseTask):
    def flow(self, localBranchName: str):
        assert not localBranchName.startswith(RefPrefix.HEADS)
        branch = self.repo.branches.local[localBranchName]
        tip = branch.target
        localName = localBranchName
        upstream = branch.upstream.shorthand if branch.upstream else ""
        yield from self._internalFlow(tip, localName, trackUpstream=upstream)


class NewTrackingBranch(_NewBranchBaseTask):
    def flow(self, remoteBranchName: str):
        assert not remoteBranchName.startswith(RefPrefix.REMOTES)
        branch = self.repo.branches.remote[remoteBranchName]
        tip = branch.target
        localName = remoteBranchName.removeprefix(branch.remote_name + "/")
        upstream = branch.shorthand
        yield from self._internalFlow(tip, localName, trackUpstream=upstream)


class EditTrackedBranch(RepoTask):
    def effects(self):
        return TaskEffects.Refs

    def flow(self, localBranchName: str):
        dlg = TrackedBranchDialog(self.repo, localBranchName, self.parentWidget())
        setWindowModal(dlg)
        yield from self.flowDialog(dlg)

        remoteBranchName = dlg.newTrackedBranchName
        dlg.deleteLater()

        # Bail if no-op
        if remoteBranchName == self.repo.branches.local[localBranchName].upstream:
            yield from self.flowAbort()

        yield from self.flowEnterWorkerThread()

        self.repo.edit_tracking_branch(localBranchName, remoteBranchName)


class FastForwardBranch(RepoTask):
    def flow(self, localBranchName: str = ""):
        if not localBranchName:
            localBranchName = self.repo.head_branch_shorthand

        try:
            branch = self.repo.branches.local[localBranchName]
        except KeyError:
            yield from self.flowAbort(self.tr("To fast-forward a branch, a local branch must be checked out. "
                                               "Try switching to a local branch before fast-forwarding it."))

        upstream: Branch = branch.upstream
        if not upstream:
            yield from self.flowAbort(self.tr("Can’t fast-forward “{0}” because it isn’t tracking a remote branch."
                                              ).format(escape(branch.shorthand)))

        remoteBranchName = upstream.shorthand

        yield from self.flowEnterWorkerThread()

        upToDate = self.repo.fast_forward_branch(localBranchName, remoteBranchName)

        ahead = False
        if upToDate:
            ahead = upstream.target != branch.target

        yield from self.flowEnterUiThread()

        if upToDate:
            message = [self.tr("No fast-forwarding necessary.")]
            if ahead:
                message.append(self.tr("Your local branch “{0}” is ahead of “{1}”.").format(
                    escape(localBranchName), escape(remoteBranchName)))
            else:
                message.append(self.tr("Your local branch “{0}” is already up-to-date with “{1}”.").format(
                    escape(localBranchName), escape(remoteBranchName)))
            showInformation(self.parentWidget(), self.name(), paragraphs(message))

    def onError(self, exc):
        if isinstance(exc, DivergentBranchesError):
            text = paragraphs(
                self.tr("Can’t fast-forward “{0}” to “{1}”.").format(exc.local_branch.shorthand, exc.remote_branch.shorthand),
                self.tr("The branches are divergent."))
            showWarning(self.parentWidget(), self.name(), text)
        else:
            super().onError(exc)

    def effects(self):
        return TaskEffects.Refs | TaskEffects.Head | TaskEffects.Workdir


class MergeBranch(RepoTask):
    def effects(self) -> TaskEffects:
        # TODO: Force refresh top of graph including the parents of the Uncommited Changes Fake Commit
        return TaskEffects.Refs | TaskEffects.Workdir | TaskEffects.ShowWorkdir

    def flow(self, them: str):
        # Run merge analysis on background thread
        yield from self.flowEnterWorkerThread()
        self.repo.refresh_index()
        anyStagedFiles = self.repo.any_staged_changes
        anyConflicts = self.repo.any_conflicts
        myBranch = self.repo.head_branch_shorthand
        theirBranch = self.repo.branches.local[them]
        target: Oid = theirBranch.target
        analysis, pref = self.repo.merge_analysis(target)

        yield from self.flowEnterUiThread()
        logger.info(f"Merge analysis: {repr(analysis)} {repr(pref)}")

        if anyConflicts:
            message = paragraphs(
                self.tr("Merging is not possible right now because you have unresolved conflicts."),
                self.tr("Fix the conflicts to proceed."))
            yield from self.flowAbort(text=message)

        elif anyStagedFiles:
            message = paragraphs(
                self.tr("Merging is not possible right now because you have staged changes."),
                self.tr("Commit your changes or stash them to proceed."))
            yield from self.flowAbort(text=message)

        elif analysis == GIT_MERGE_ANALYSIS_UP_TO_DATE:
            message = paragraphs(
                self.tr("No merge is necessary."),
                self.tr("Your branch “{0}” is already up-to-date with “{1}”.").format(myBranch, them))
            yield from self.flowAbort(text=message)

        elif analysis == GIT_MERGE_ANALYSIS_UNBORN:
            message = self.tr("Cannot merge into an unborn head.")
            yield from self.flowAbort(text=message)

        elif analysis == GIT_MERGE_ANALYSIS_FASTFORWARD | GIT_MERGE_ANALYSIS_NORMAL:
            message = self.tr("There are no merge conflicts. Your branch <b>“{0}”</b> can be "
                              "fast-forwarded to <b>“{1}”</b>.").format(myBranch, them)
            details = self.tr("Fast-forwarding means that the tip of your branch will be moved "
                              "to a more recent commit in a linear path without requiring a merge. "
                              "In this case, “{0}” will be fast-forwarded to “{1}”."
                              ).format(myBranch, shortHash(target))
            yield from self.flowConfirm(text=message, verb=self.tr("Fast-Forward"), detailText=details)
            self.repo.fast_forward_branch(myBranch, theirBranch.name)

        elif analysis == GIT_MERGE_ANALYSIS_NORMAL:
            message = paragraphs(
                self.tr("Merging <b>“{0}”</b> into <b>“{1}”</b> will cause conflicts.").format(them, myBranch),
                self.tr("You will need to fix the conflicts. Then, commit the result to conclude the merge."))
            yield from self.flowConfirm(text=message, verb=self.tr("Merge"))
            self.repo.merge(target)

        else:
            yield from self.flowAbort(escape(f"Unsupported MergeAnalysis! ma={repr(analysis)} mp={repr(pref)}"))


class RecallCommit(RepoTask):
    def effects(self) -> TaskEffects:
        return TaskEffects.Refs

    def flow(self):
        dlg = showTextInputDialog(
            self.parentWidget(),
            self.tr("Recall lost commit"),
            self.tr("If you know the hash of a commit that isn’t part of any branches,<br>"
                    "{0} will try to recall it for you.").format(qAppName()),
            okButtonText=self.tr("Recall"),
            deleteOnClose=False)

        yield from self.flowDialog(dlg)
        dlg.deleteLater()

        # Naked name, NOT prefixed with the name of the remote
        needle = dlg.lineEdit.text()

        yield from self.flowEnterWorkerThread()

        obj = self.repo[needle]
        commit: Commit = obj.peel(Commit)

        branchName = f"recall-{commit.hex}"
        self.repo.create_branch_from_commit(branchName, commit.oid)

        yield from self.flowEnterUiThread()

        showInformation(
            self.parentWidget(),
            self.tr("Recall lost commit"),
            paragraphs(
                self.tr("Hurray, the commit was found! Find it on this branch:"),
                "<b>{0}</b>".format(escape(branchName))
            ))
