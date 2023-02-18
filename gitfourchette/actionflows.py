from gitfourchette import porcelain
from gitfourchette.qt import *
from gitfourchette.util import messageSummary, shortHash, stockIcon, asyncMessageBox, showWarning, setWindowModal
from gitfourchette.widgets.brandeddialog import showTextInputDialog
from gitfourchette.widgets.commitdialog import CommitDialog
from gitfourchette.widgets.newbranchdialog import NewBranchDialog
from gitfourchette.widgets.pushdialog import PushDialog
from gitfourchette.widgets.remotedialog import RemoteDialog
from gitfourchette.widgets.stashdialog import StashDialog
from gitfourchette.widgets.trackedbranchdialog import TrackedBranchDialog
from html import escape
import pygit2


class ActionFlows(QObject):
    pullBranch = Signal(str, str)  # local branch, remote ref to pull
    pushComplete = Signal()

    def __init__(self, repo: pygit2.Repository, parent: QWidget):
        super().__init__(parent)
        self.repo = repo
        self.parentWidget = parent

    # -------------------------------------------------------------------------
    # Branch

    def _newBranchFlowInternal(self, tip: pygit2.Oid, originalBranchName: str, trackingCandidates: list[str] = []):
        commitMessage = porcelain.getCommitMessage(self.repo, tip)
        commitMessage, junk = messageSummary(commitMessage)

        dlg = NewBranchDialog(
            originalBranchName,
            shortHash(tip),
            commitMessage,
            trackingCandidates=trackingCandidates,
            forbiddenBranchNames=[""] + self.repo.listall_branches(pygit2.GIT_BRANCH_LOCAL),
            parent=self.parentWidget)

        def onAccept():
            localName = dlg.ui.nameEdit.text()
            trackingBranch = ""
            switchTo = dlg.ui.switchToBranchCheckBox.isChecked()

            if dlg.ui.trackRemoteBranchCheckBox.isChecked():
                trackingBranch = dlg.ui.trackRemoteBranchComboBox.currentText()

            self.newBranch.emit(localName, tip, trackingBranch, switchTo)

        dlg.accepted.connect(onAccept)

        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        setWindowModal(dlg)
        dlg.show()
        dlg.setMaximumHeight(dlg.height())

    def newBranchFromCommitFlow(self, tip: pygit2.Oid):
        HEADS_PREFIX = "refs/heads/"
        REMOTES_PREFIX = "refs/remotes/"

        initialName = ""
        trackingCandidates = []

        # If we're creating a branch at the tip of the current branch, default to its name
        if (not self.repo.head_is_unborn
                and not self.repo.head_is_detached
                and self.repo.head.target == tip):
            initialName = self.repo.head.shorthand

        refsPointingHere = porcelain.mapCommitsToReferences(self.repo)[tip]

        # Collect remote-tracking branch candidates and set initialName
        for r in refsPointingHere:
            if r.startswith(HEADS_PREFIX):
                branchName = r.removeprefix(HEADS_PREFIX)
                if not initialName:
                    initialName = branchName

                branch = self.repo.branches[branchName]
                if branch.upstream and branch.upstream.shorthand not in trackingCandidates:
                    trackingCandidates.append(branch.upstream.shorthand)

            elif r.startswith(REMOTES_PREFIX):
                shorthand = r.removeprefix(REMOTES_PREFIX)
                if not initialName:
                    _, initialName = porcelain.splitRemoteBranchShorthand(shorthand)
                if shorthand not in trackingCandidates:
                    trackingCandidates.append(shorthand)

        self._newBranchFlowInternal(tip, initialName, trackingCandidates=trackingCandidates)

    def newBranchFromBranchFlow(self, originalBranchName: str):
        branch = self.repo.branches[originalBranchName]
        trackingCandidates = []
        if branch.upstream:
            trackingCandidates = [branch.upstream.shorthand]
        tip: pygit2.Oid = branch.target
        self._newBranchFlowInternal(tip, originalBranchName, trackingCandidates)

    # -------------------------------------------------------------------------
    # Push

    def pushFlow(self, branchName: str = None):
        if not branchName:
            branchName = porcelain.getActiveBranchShorthand(self.repo)

        try:
            branch = self.repo.branches.local[branchName]
        except KeyError:
            showWarning(self.parentWidget, self.tr("No branch to push"),
                        self.tr("To push, you must be on a local branch. Try switching to a local branch first."))
            return

        dlg = PushDialog(self.repo, branch, self.parentWidget)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dlg.accepted.connect(self.pushComplete)
        dlg.show()
        return dlg

    # -------------------------------------------------------------------------
    # Pull

    def pullFlow(self, branchName: str = None):
        if not branchName:
            branchName = porcelain.getActiveBranchShorthand(self.repo)

        try:
            branch = self.repo.branches.local[branchName]
        except KeyError:
            showWarning(self.parentWidget, self.tr("No branch to pull"),
                        self.tr("To pull, you must be on a local branch. Try switching to a local branch first."))
            return

        bu: pygit2.Branch = branch.upstream
        if not bu:
            showWarning(self.parentWidget, self.tr("No remote-tracking branch"),
                        self.tr("Can’t pull because “{0}” isn’t tracking a remote branch.").format(escape(branch.shorthand)))
            return

        self.pullBranch.emit(branch.branch_name, bu.shorthand)
