from gitfourchette import porcelain
from gitfourchette.qt import *
from gitfourchette.util import labelQuote, messageSummary, shortHash, stockIcon
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
    amendCommit = Signal(str, object, object)
    createCommit = Signal(str, object, object)
    deleteBranch = Signal(str)
    deleteRemote = Signal(str)
    deleteRemoteBranch = Signal(str)
    discardFiles = Signal(list)  # list[Patch]
    editRemote = Signal(str, str, str)  # oldName, newName, newURL
    editTrackingBranch = Signal(str, str)
    newBranch = Signal(str, pygit2.Oid, str, bool)  # name, commit oid, tracking branch, switch to
    newRemote = Signal(str, str)  # name, url
    newTrackingBranch = Signal(str, str)
    renameBranch = Signal(str, str)
    pullBranch = Signal(str, str)  # local branch, remote ref to pull
    updateCommitDraftMessage = Signal(str)

    pushComplete = Signal()

    newStash = Signal(str, str)

    def __init__(self, repo: pygit2.Repository, parent: QWidget):
        super().__init__(parent)
        self.repo = repo
        self.parentWidget = parent

    def confirmAction(
            self,
            title: str,
            text: str,
            acceptButtonIcon: (QStyle.StandardPixmap | str | None) = None
    ) -> QMessageBox:

        qmb = QMessageBox(
            QMessageBox.Icon.Question,
            title,
            text,
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            parent=self.parentWidget)

        qmb.setWindowModality(Qt.WindowModality.WindowModal)

        # Using QMessageBox.StandardButton.Ok instead of QMessageBox.StandardButton.Discard so it connects to the "accepted" signal.
        yes: QAbstractButton = qmb.button(QMessageBox.StandardButton.Ok)
        if acceptButtonIcon:
            yes.setIcon(stockIcon(acceptButtonIcon))
        yes.setText(title)

        qmb.setDefaultButton(yes)
        qmb.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)  # don't leak dialog
        qmb.show()

        return qmb

    # -------------------------------------------------------------------------
    # Staging area

    def discardFilesFlow(self, entries: list[pygit2.Patch]):
        if len(entries) == 1:
            question = F"Really discard changes to {entries[0].delta.new_file.path}?"
        else:
            question = F"Really discard changes to {len(entries)} files?"

        qmb = self.confirmAction(
            "Discard changes",
            F"{question}\nThis cannot be undone!",
            QStyle.StandardPixmap.SP_DialogDiscardButton)
        qmb.accepted.connect(lambda: self.discardFiles.emit(entries))
        return qmb

    # -------------------------------------------------------------------------
    # Branch

    def newBranchFlowInternal(self, tip: pygit2.Oid, originalBranchName: str):
        commitMessage = porcelain.getCommitMessage(self.repo, tip)
        commitMessage, junk = messageSummary(commitMessage)

        dlg = NewBranchDialog(
            originalBranchName,
            shortHash(tip),
            commitMessage,
            trackingCandidates=[],
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

        dlg.setWindowModality(Qt.WindowModality.WindowModal)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dlg.show()
        dlg.setMaximumHeight(dlg.height())

    def newBranchFromCommitFlow(self, tip: pygit2.Oid):
        initialName = ""

        # If we're creating a branch at the tip of the current branch, default to its name
        if (not self.repo.head_is_unborn
                and not self.repo.head_is_detached
                and self.repo.head.target == tip):
            initialName = self.repo.head.shorthand
        else:
            # If a ref points to this commit, pre-fill the input field with the ref's name
            try:
                refsPointingHere = porcelain.mapCommitsToReferences(self.repo)[tip]
                candidates = (r for r in refsPointingHere if r.startswith(('refs/heads/', 'refs/remotes/')))
                initialName = next(candidates).split('/')[-1]
            except (KeyError, StopIteration):
                pass

        self.newBranchFlowInternal(tip, initialName)

    def newBranchFlow(self):
        branchTip = porcelain.getHeadCommit(self.repo).oid
        self.newBranchFromCommitFlow(branchTip)

    def newBranchFromBranchFlow(self, originalBranchName: str):
        branch = self.repo.branches[originalBranchName]
        tip: pygit2.Oid = branch.target
        self.newBranchFlowInternal(tip, originalBranchName)

    def newTrackingBranchFlow(self, remoteBranchName: str):
        def onAccept(localBranchName):
            self.newTrackingBranch.emit(localBranchName, remoteBranchName)

        return showTextInputDialog(
            self.parentWidget,
            f"New branch tracking {labelQuote(remoteBranchName)}",
            F"Enter name for a new local branch that will\ntrack remote branch {labelQuote(remoteBranchName)}:",
            remoteBranchName[remoteBranchName.rfind('/') + 1:],
            onAccept,
            okButtonText="Create")

    def editTrackingBranchFlow(self, localBranchName: str):
        dlg = TrackedBranchDialog(self.repo, localBranchName, self.parentWidget)

        def onAccept():
            self.editTrackingBranch.emit(localBranchName, dlg.newTrackedBranchName)

        dlg.accepted.connect(onAccept)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)  # don't leak dialog
        dlg.show()

        return dlg

    def renameBranchFlow(self, oldName: str):
        def onAccept(newName):
            self.renameBranch.emit(oldName, newName)

        return showTextInputDialog(
            self.parentWidget,
            F"Rename branch {labelQuote(oldName)}",
            "Enter new name:",
            oldName,
            onAccept,
            okButtonText="Rename")

    def deleteBranchFlow(self, localBranchName: str):
        qmb = self.confirmAction(
            "Delete branch",
            F"Really delete local branch <b>{labelQuote(localBranchName)}</b>?<br/>This cannot be undone!",
            QStyle.StandardPixmap.SP_DialogDiscardButton)
        qmb.accepted.connect(lambda: self.deleteBranch.emit(localBranchName))
        return qmb

    # -------------------------------------------------------------------------
    # Remote

    def newRemoteFlow(self) -> RemoteDialog:
        def onAccept(newName, newURL):
            self.newRemote.emit(newName, newURL)

        dlg = RemoteDialog(False, "", "", self.parentWidget)
        dlg.accepted.connect(lambda: onAccept(dlg.ui.nameEdit.text(), dlg.ui.urlEdit.text()))
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)  # don't leak dialog
        dlg.show()
        return dlg

    def editRemoteFlow(self, remoteName: str) -> RemoteDialog:
        def onAccept(newName, newURL):
            self.editRemote.emit(remoteName, newName, newURL)

        dlg = RemoteDialog(True, remoteName, self.repo.remotes[remoteName].url, self.parentWidget)
        dlg.accepted.connect(lambda: onAccept(dlg.ui.nameEdit.text(), dlg.ui.urlEdit.text()))
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)  # don't leak dialog
        dlg.show()
        return dlg

    def deleteRemoteFlow(self, remoteName: str):
        qmb = self.confirmAction(
            "Delete remote",
            F"Really delete remote <b>{labelQuote(remoteName)}</b>?<br/>This cannot be undone!",
            QStyle.StandardPixmap.SP_DialogDiscardButton)
        qmb.accepted.connect(lambda: self.deleteRemote.emit(remoteName))
        return qmb

    def deleteRemoteBranchFlow(self, remoteBranchName: str):
        qmb = self.confirmAction(
            "Delete branch on remote",
            (f"Really delete branch <b>{labelQuote(remoteBranchName)}</b> from the remote repository?<br/>"
            f"This cannot be undone!"),
            QStyle.StandardPixmap.SP_DialogDiscardButton)
        qmb.accepted.connect(lambda: self.deleteRemoteBranch.emit(remoteBranchName))
        return qmb

    # -------------------------------------------------------------------------
    # Commit, amend

    def emptyCommitFlow(self, initialText: str):
        qmb = self.confirmAction(
            "Create empty commit",
            "No files are staged for commit.\nDo you want to create an empty commit anyway?")
        qmb.accepted.connect(lambda: self.commitFlow(initialText, bypassEmptyCommitCheck=True))
        return qmb

    def commitFlow(self, initialMessage: str, bypassEmptyCommitCheck=False):
        if not bypassEmptyCommitCheck and not porcelain.hasAnyStagedChanges(self.repo):
            self.emptyCommitFlow(initialMessage)
            return

        sig = self.repo.default_signature

        cd = CommitDialog(
            initialText=initialMessage,
            authorSignature=sig,
            committerSignature=sig,
            isAmend=False,
            parent=self.parentWidget)

        def onAccept():
            message = cd.getFullMessage()
            author = cd.getOverriddenAuthorSignature()
            committer = cd.getOverriddenCommitterSignature()
            self.createCommit.emit(message, author, committer)

        def onReject():
            # Save draft message for next time
            self.updateCommitDraftMessage.emit(cd.getFullMessage())

        cd.accepted.connect(onAccept)
        cd.rejected.connect(onReject)
        cd.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)  # don't leak dialog
        cd.setWindowModality(Qt.WindowModality.WindowModal)
        cd.show()
        return cd

    def amendFlow(self):
        headCommit = porcelain.getHeadCommit(self.repo)

        cd = CommitDialog(
            initialText=headCommit.message,
            authorSignature=headCommit.author,
            committerSignature=self.repo.default_signature,
            isAmend=True,
            parent=self.parentWidget)

        def onAccept():
            message = cd.getFullMessage()
            author = cd.getOverriddenAuthorSignature()
            committer = cd.getOverriddenCommitterSignature()
            self.amendCommit.emit(message, author, committer)

        cd.accepted.connect(onAccept)
        cd.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)  # don't leak dialog
        cd.setWindowModality(Qt.WindowModality.WindowModal)
        cd.show()
        return cd

    # -------------------------------------------------------------------------
    # Push

    def pushFlow(self, branchName: str = None):
        if not branchName:
            branchName = porcelain.getActiveBranchShorthand(self.repo)

        try:
            branch = self.repo.branches.local[branchName]
        except KeyError:
            QMessageBox.warning(
                self.parentWidget, "No Branch to Push",
                "No valid local branch to push. Try switching to a local branch first.")
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
            QMessageBox.warning(
                self.parentWidget, "No Branch to Which to Pull",
                "No valid local branch to which to pull. Try switching to a local branch first.")
            return

        bu: pygit2.Branch = branch.upstream
        if not bu:
            QMessageBox.warning(
                self.parentWidget, "No Remote-Tracking Branch",
                F"Can’t pull because “{branch.shorthand}” doesn’t track a remote branch.")
            return

        self.pullBranch.emit(branch.branch_name, bu.shorthand)

    # -------------------------------------------------------------------------
    # Stash

    def newStashFlow(self):
        def onAccepted():
            message = dlg.ui.messageEdit.text()
            flags = ""
            if dlg.ui.keepIndexCheckBox.isChecked():
                flags += "k"
            if dlg.ui.includeUntrackedCheckBox.isChecked():
                flags += "u"
            if dlg.ui.includeIgnoredCheckBox.isChecked():
                flags += "i"
            self.newStash.emit(message, flags)

        dlg = StashDialog(self.parentWidget)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dlg.accepted.connect(onAccepted)
        dlg.show()
        return dlg
