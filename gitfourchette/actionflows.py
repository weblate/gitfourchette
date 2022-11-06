from gitfourchette import porcelain
from gitfourchette.qt import *
from gitfourchette.util import messageSummary, shortHash, stockIcon, asyncMessageBox, showWarning
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
    renameRemoteBranch = Signal(str, str)
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

        qmb = asyncMessageBox(
            self.parentWidget,
            'question',
            title,
            text,
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)

        # Using QMessageBox.StandardButton.Ok instead of QMessageBox.StandardButton.Discard
        # so it connects to the "accepted" signal.
        yes: QAbstractButton = qmb.button(QMessageBox.StandardButton.Ok)
        if acceptButtonIcon:
            yes.setIcon(stockIcon(acceptButtonIcon))
        yes.setText(title)

        qmb.show()
        return qmb

    # -------------------------------------------------------------------------
    # Staging area

    def discardFilesFlow(self, entries: list[pygit2.Patch]):
        if len(entries) == 1:
            path = entries[0].delta.new_file.path
            text = self.tr("Really discard changes to <b>“{0}”</b>?").format(escape(path))
        else:
            text = self.tr("Really discard changes to <b>%n files</b>?", "", len(entries))
        text += "<br>" + translate("Global", "This cannot be undone!")

        qmb = self.confirmAction(self.tr("Discard changes"), text,
                                 QStyle.StandardPixmap.SP_DialogDiscardButton)
        qmb.accepted.connect(lambda: self.discardFiles.emit(entries))
        return qmb

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

        dlg.setWindowModality(Qt.WindowModality.WindowModal)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
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

    def newBranchFlow(self):
        branchTip = porcelain.getHeadCommit(self.repo).oid
        self.newBranchFromCommitFlow(branchTip)

    def newBranchFromBranchFlow(self, originalBranchName: str):
        branch = self.repo.branches[originalBranchName]
        trackingCandidates = []
        if branch.upstream:
            trackingCandidates = [branch.upstream.shorthand]
        tip: pygit2.Oid = branch.target
        self._newBranchFlowInternal(tip, originalBranchName, trackingCandidates)

    def newTrackingBranchFlow(self, remoteBranchName: str):
        def onAccept(localBranchName):
            self.newTrackingBranch.emit(localBranchName, remoteBranchName)

        return showTextInputDialog(
            self.parentWidget,
            self.tr("New branch tracking “{0}”").format(escape(remoteBranchName)),
            self.tr("Enter name for a new local branch that will<br>track remote branch “{0}”:").format(escape(remoteBranchName)),
            remoteBranchName[remoteBranchName.rfind('/') + 1:],
            onAccept,
            okButtonText=self.tr("Create"))

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
            self.tr("Rename branch “{0}”").format(escape(oldName)),
            self.tr("Enter new name:"),
            oldName,
            onAccept,
            okButtonText=self.tr("Rename"))

    def deleteBranchFlow(self, localBranchName: str):
        text = self.tr("Really delete local branch <b>“{0}”</b>?").format(escape(localBranchName))
        text += "<br>" + translate("Global", "This cannot be undone!")

        qmb = self.confirmAction(self.tr("Delete branch"), text,
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
        dlg.setWindowModality(Qt.WindowModality.WindowModal)
        dlg.show()
        dlg.setMaximumHeight(dlg.height())
        return dlg

    def editRemoteFlow(self, remoteName: str) -> RemoteDialog:
        def onAccept(newName, newURL):
            self.editRemote.emit(remoteName, newName, newURL)

        dlg = RemoteDialog(True, remoteName, self.repo.remotes[remoteName].url, self.parentWidget)
        dlg.accepted.connect(lambda: onAccept(dlg.ui.nameEdit.text(), dlg.ui.urlEdit.text()))
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)  # don't leak dialog
        dlg.setWindowModality(Qt.WindowModality.WindowModal)
        dlg.show()
        dlg.setMaximumHeight(dlg.height())
        return dlg

    def deleteRemoteFlow(self, remoteName: str):
        text = (self.tr("Really delete remote <b>“{0}”</b>?").format(escape(remoteName))
                + "<br>" + translate("Global", "This cannot be undone!"))

        qmb = self.confirmAction(self.tr("Delete remote"), text, QStyle.StandardPixmap.SP_DialogDiscardButton)
        qmb.accepted.connect(lambda: self.deleteRemote.emit(remoteName))
        return qmb

    def renameRemoteBranchFlow(self, remoteBranchName: str):
        def onAccept(newName):
            self.renameRemoteBranch.emit(remoteBranchName, newName)

        remoteName, branchName = porcelain.splitRemoteBranchShorthand(remoteBranchName)

        return showTextInputDialog(
            self.parentWidget,
            self.tr("Rename remote branch “{0}”").format(escape(remoteBranchName)),
            self.tr("Enter new name:"),
            branchName,
            onAccept,
            okButtonText=self.tr("Rename on remote"))

    def deleteRemoteBranchFlow(self, remoteBranchName: str):
        text = (self.tr("Really delete branch <b>“{0}”</b> from the remote repository?").format(escape(remoteBranchName))
                + "<br>" + translate("Global", "This cannot be undone!"))

        qmb = self.confirmAction(self.tr("Delete Branch on Remote"), text,
                                 QStyle.StandardPixmap.SP_DialogDiscardButton)
        qmb.accepted.connect(lambda: self.deleteRemoteBranch.emit(remoteBranchName))
        return qmb

    # -------------------------------------------------------------------------
    # Commit, amend

    def emptyCommitFlow(self, initialText: str):
        qmb = self.confirmAction(
            self.tr("Create empty commit"),
            self.tr("No files are staged for commit.<br>Do you want to create an empty commit anyway?"))
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
            showWarning(self, self.tr("No branch to push"),
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
            showWarning(self, self.tr("No branch to pull"),
                        self.tr("To pull, you must be on a local branch. Try switching to a local branch first."))
            return

        bu: pygit2.Branch = branch.upstream
        if not bu:
            showWarning(self, self.tr("No remote-tracking branch"),
                        self.tr("Can’t pull because “{0}” isn’t tracking a remote branch.").format(escape(branch.shorthand)))
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
        dlg.setWindowModality(Qt.WindowModality.WindowModal)
        dlg.accepted.connect(onAccepted)
        dlg.show()
        dlg.setMaximumHeight(dlg.height())
        return dlg
