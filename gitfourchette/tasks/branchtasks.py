from gitfourchette import porcelain
from gitfourchette import util
from gitfourchette.porcelain import HEADS_PREFIX, REMOTES_PREFIX
from gitfourchette.qt import *
from gitfourchette.tasks.repotask import RepoTask, TaskAffectsWhat
from gitfourchette.widgets.brandeddialog import showTextInputDialog
from gitfourchette.widgets.newbranchdialog import NewBranchDialog, validateLocalBranchName
from gitfourchette.widgets.trackedbranchdialog import TrackedBranchDialog
from html import escape
import pygit2


class SwitchBranch(RepoTask):
    def name(self):
        return translate("Operation", "Switch to branch")

    def refreshWhat(self):
        return TaskAffectsWhat.LOCALREFS | TaskAffectsWhat.HEAD

    def flow(self, newBranch: str, askForConfirmation: bool):
        assert not newBranch.startswith(HEADS_PREFIX)

        if askForConfirmation:
            text = self.tr("Do you want to switch to branch <b>“{0}”</b>?").format(escape(newBranch))
            verb = self.tr("Switch")
            yield from self._flowConfirm(text=text, verb=verb)

        yield from self._flowBeginWorkerThread()
        porcelain.checkoutLocalBranch(self.repo, newBranch)


class RenameBranch(RepoTask):
    def name(self):
        return translate("Operation", "Rename local branch")

    def flow(self, oldBranchName: str):
        assert not oldBranchName.startswith(HEADS_PREFIX)

        forbiddenBranchNames = self.repo.listall_branches(pygit2.GIT_BRANCH_LOCAL)
        forbiddenBranchNames.remove(oldBranchName)

        dlg = showTextInputDialog(
            self.parent(),
            self.tr("Rename local branch “{0}”").format(escape(oldBranchName)),
            self.tr("Enter new name:"),
            oldBranchName,
            okButtonText=self.tr("Rename"),
            validatorFunc=lambda name: validateLocalBranchName(name, forbiddenBranchNames))

        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        yield from self._flowDialog(dlg)
        dlg.deleteLater()
        newBranchName = dlg.lineEdit.text()

        yield from self._flowBeginWorkerThread()
        porcelain.renameBranch(self.repo, oldBranchName, newBranchName)

    def refreshWhat(self):
        return TaskAffectsWhat.LOCALREFS


class DeleteBranch(RepoTask):
    def name(self):
        return translate("Operation", "Delete local branch")

    def flow(self, localBranchName: str):
        assert not localBranchName.startswith(HEADS_PREFIX)

        text = util.paragraphs(self.tr("Really delete local branch <b>“{0}”</b>?").format(escape(localBranchName)),
                               translate("Global", "This cannot be undone!"))

        yield from self._flowConfirm(
            text=text,
            verb=self.tr("Delete branch", "Button label"),
            buttonIcon=QStyle.StandardPixmap.SP_DialogDiscardButton)

        yield from self._flowBeginWorkerThread()
        porcelain.deleteBranch(self.repo, localBranchName)

    def refreshWhat(self):
        return TaskAffectsWhat.LOCALREFS


class _NewBranchBaseTask(RepoTask):
    def name(self):
        return translate("Operation", "New local branch")

    def _internalFlow(self, tip: pygit2.Oid, localName: str = "", switchTo: bool = False, upstream: str = ""):
        repo = self.repo

        # If we're creating a branch at the tip of the current branch, default to its name
        if (not localName
                and not repo.head_is_unborn
                and not repo.head_is_detached
                and repo.head.target == tip):
            localName = repo.head.shorthand

        # Collect upstream names and set initial localName (if we haven't been able to set it above).
        refsPointingHere = porcelain.refsPointingAtCommit(repo, tip)
        upstreams = []
        for r in refsPointingHere:
            if r.startswith(HEADS_PREFIX):
                branchName = r.removeprefix(HEADS_PREFIX)
                if not localName:
                    localName = branchName
                branch = repo.branches[branchName]
                if branch.upstream:
                    upstreams.append(branch.upstream.shorthand)

            elif r.startswith(REMOTES_PREFIX):
                shorthand = r.removeprefix(REMOTES_PREFIX)
                if not localName:
                    _, localName = porcelain.splitRemoteBranchShorthand(shorthand)
                upstreams.append(shorthand)

        # Ensure no duplicates (stable order since Python 3.7+)
        upstreams = list(dict.fromkeys(upstreams))

        forbiddenBranchNames = repo.listall_branches(pygit2.GIT_BRANCH_LOCAL)

        commitMessage = porcelain.getCommitMessage(repo, tip)
        commitMessage, junk = util.messageSummary(commitMessage)

        dlg = NewBranchDialog(
            initialName=localName,
            target=util.shortHash(tip),
            targetSubtitle=commitMessage,
            upstreams=upstreams,
            forbiddenBranchNames=forbiddenBranchNames,
            parent=self.parent())

        if upstream:
            i = dlg.ui.upstreamComboBox.findText(upstream)
            if i >= 0:
                dlg.ui.upstreamComboBox.setCurrentIndex(i)
                if switchTo:
                    dlg.ui.upstreamCheckBox.setChecked(True)

        util.setWindowModal(dlg)
        dlg.show()
        dlg.setMaximumHeight(dlg.height())
        yield from self._flowDialog(dlg)
        dlg.deleteLater()

        localName = dlg.ui.nameEdit.text()
        upstream = ""
        switchTo = dlg.ui.switchToBranchCheckBox.isChecked()
        if dlg.ui.upstreamCheckBox.isChecked():
            upstream = dlg.ui.upstreamComboBox.currentText()

        yield from self._flowBeginWorkerThread()

        # Create local branch
        porcelain.newBranchFromCommit(repo, localName, tip, switchTo=False)

        # Optionally make it track a remote branch
        if upstream:
            porcelain.editTrackingBranch(repo, localName, upstream)

        # Switch to it last (if user wants to)
        if switchTo:
            porcelain.checkoutLocalBranch(repo, localName)

    def refreshWhat(self):
        return TaskAffectsWhat.LOCALREFS


class NewBranchFromHead(_NewBranchBaseTask):
    def flow(self):
        tip = porcelain.getHeadCommit(self.repo).oid
        yield from self._internalFlow(tip)


class NewBranchFromCommit(_NewBranchBaseTask):
    def flow(self, tip: pygit2.Oid):
        yield from self._internalFlow(tip)


class NewBranchFromLocalBranch(_NewBranchBaseTask):
    def flow(self, localBranchName: str):
        assert not localBranchName.startswith(HEADS_PREFIX)
        branch = self.repo.branches.local[localBranchName]
        tip = branch.target
        localName = localBranchName
        upstream = branch.upstream.shorthand if branch.upstream else ""
        yield from self._internalFlow(tip, localName, False, upstream)


class NewTrackingBranch(_NewBranchBaseTask):
    def flow(self, remoteBranchName: str):
        assert not remoteBranchName.startswith(REMOTES_PREFIX)
        branch = self.repo.branches.remote[remoteBranchName]
        tip = branch.target
        localName = remoteBranchName.removeprefix(branch.remote_name + "/")
        upstream = branch.shorthand
        switchTo = True
        yield from self._internalFlow(tip, localName, switchTo, upstream)


class EditTrackedBranch(RepoTask):
    def name(self):
        return translate("Operation", "Change remote branch tracked by local branch")

    def refreshWhat(self):
        return TaskAffectsWhat.LOCALREFS

    def flow(self, localBranchName: str):
        dlg = TrackedBranchDialog(self.repo, localBranchName, self.parent())
        util.setWindowModal(dlg)
        dlg.show()
        yield from self._flowDialog(dlg)

        remoteBranchName = dlg.newTrackedBranchName
        dlg.deleteLater()

        # Bail if no-op
        if remoteBranchName == self.repo.branches.local[localBranchName].upstream:
            yield from self._flowAbort()

        yield from self._flowBeginWorkerThread()

        porcelain.editTrackingBranch(self.repo, localBranchName, remoteBranchName)


# TODO: That's a confusing name because this task doesn't perform net access, unlike git's "pull" operation. We'll need to change porcelain.pull as well.
class PullBranch(RepoTask):
    def name(self):
        return translate("Operation", "Pull branch")

    def flow(self, localBranchName: str):
        if not localBranchName:
            localBranchName = porcelain.getActiveBranchShorthand(self.repo)

        try:
            branch = self.repo.branches.local[localBranchName]
        except KeyError:
            raise ValueError(self.tr("To pull, you must be on a local branch. Try switching to a local branch first."))

        bu: pygit2.Branch = branch.upstream
        if not bu:
            raise ValueError(self.tr("Can’t pull because “{0}” isn’t tracking a remote branch.").format(escape(branch.shorthand)))

        remoteBranchName = bu.shorthand

        yield from self._flowBeginWorkerThread()

        porcelain.pull(self.repo, localBranchName, remoteBranchName)

    def onError(self, exc):
        if isinstance(exc, porcelain.DivergentBranchesError):
            text = util.paragraphs(
                self.tr("Can’t fast-forward “{0}” to “{1}”.").format(exc.localBranch.shorthand, exc.remoteBranch.shorthand),
                self.tr("The branches are divergent."))
            util.showWarning(self.parent(), self.name(), text)
        else:
            super().onError(exc)

    def refreshWhat(self):
        return TaskAffectsWhat.LOCALREFS | TaskAffectsWhat.HEAD

