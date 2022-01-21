import porcelain
from allqt import *
from util import labelQuote, excMessageBox
from widgets.brandeddialog import showTextInputDialog
from widgets.commitdialog import CommitDialog
from widgets.remotedialog import RemoteDialog
from widgets.trackedbranchdialog import TrackedBranchDialog
import pygit2


class ActionFlows(QObject):
    amendCommit = Signal(str, object, object)
    createCommit = Signal(str, object, object)
    deleteBranch = Signal(str)
    deleteRemote = Signal(str)
    discardFiles = Signal(list)  # list[Patch]
    editRemote = Signal(str, str, str)  # oldName, newName, newURL
    editTrackingBranch = Signal(str, str)
    newBranch = Signal(str)
    newTrackingBranch = Signal(str, str)
    pushBranch = Signal(str)
    renameBranch = Signal(str, str)
    updateCommitDraftMessage = Signal(str)

    def __init__(self, repo: pygit2.Repository, parent: QWidget):
        super().__init__(parent)
        self.repo = repo
        self.parentWidget = parent

    # -------------------------------------------------------------------------
    # Staging area

    def discardFilesFlow(self, entries: list[pygit2.Patch]):
        if len(entries) == 1:
            question = F"Really discard changes to {entries[0].delta.new_file.path}?"
        else:
            question = F"Really discard changes to {len(entries)} files?"

        qmb = QMessageBox(
            QMessageBox.Question,
            "Discard changes",
            F"{question}\nThis cannot be undone!",
            QMessageBox.Ok | QMessageBox.Cancel,
            parent=self.parentWidget)

        # Using QMessageBox.Ok instead of QMessageBox.Discard so it connects to the "accepted" signal.
        yes: QAbstractButton = qmb.button(QMessageBox.Ok)
        yes.setIcon(self.parentWidget.style().standardIcon(QStyle.SP_DialogDiscardButton))
        yes.setText("Discard changes")

        qmb.accepted.connect(lambda: self.discardFiles.emit(entries))
        qmb.setDefaultButton(yes)

        qmb.setAttribute(Qt.WA_DeleteOnClose)  # don't leak dialog
        qmb.show()

    # -------------------------------------------------------------------------
    # Branch

    def newBranchFlow(self):
        def onAccept(newBranchName):
            self.newBranch.emit(newBranchName)

        return showTextInputDialog(
            self.parentWidget,
            "New branch",
            "Enter name for new branch:",
            None,
            onAccept)

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
        dlg.setAttribute(Qt.WA_DeleteOnClose)  # don't leak dialog
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
        qmb = QMessageBox(
            QMessageBox.Warning,
            "Delete Branch",
            F"Really delete local branch <b>{labelQuote(localBranchName)}</b>?<br/>This cannot be undone!",
            QMessageBox.Discard | QMessageBox.Cancel,
            parent=self.parentWidget)
        qmb.button(QMessageBox.Discard).setText("Delete")
        qmb.setAttribute(Qt.WA_DeleteOnClose)  # don't leak dialog
        qmb.accepted.connect(lambda: self.deleteBranch.emit(localBranchName))
        qmb.show()
        return qmb

    # -------------------------------------------------------------------------
    # Remote

    def editRemoteFlow(self, remoteName: str) -> RemoteDialog:
        def onAccept(newName, newURL):
            self.editRemote.emit(remoteName, newName, newURL)

        dlg = RemoteDialog(remoteName, self.repo.remotes[remoteName].url, self.parentWidget)
        dlg.accepted.connect(lambda: onAccept(dlg.ui.nameEdit.text(), dlg.ui.urlEdit.text()))
        dlg.setAttribute(Qt.WA_DeleteOnClose)  # don't leak dialog
        dlg.show()
        return dlg

    def deleteRemoteFlow(self, remoteName: str, parent: QWidget):
        rc = QMessageBox.warning(parent, "Delete Remote",
                                 F"Really delete remote <b>{labelQuote(remoteName)}</b>?"
                                 F"<br>This cannot be undone!",
                                 QMessageBox.Discard | QMessageBox.Cancel)
        if rc == QMessageBox.Discard:
            self.deleteRemote.emit(remoteName)

    # -------------------------------------------------------------------------
    # Commit, amend

    def emptyCommitFlow(self, initialText: str):
        qmb = QMessageBox(
            QMessageBox.Question,
            "Empty Commit",
            "No files are staged for commit.\nDo you want to create an empty commit anyway?",
            parent=self.parentWidget)
        ok = qmb.addButton("Go back", QMessageBox.AcceptRole)
        emptyCommit = qmb.addButton("Create empty commit", QMessageBox.ActionRole)
        qmb.setDefaultButton(ok)
        qmb.setEscapeButton(ok)
        emptyCommit.clicked.connect(lambda: self.commitFlow(initialText, bypassEmptyCommitCheck=True))
        qmb.setAttribute(Qt.WA_DeleteOnClose)  # don't leak dialog
        qmb.show()
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
            #self.state.setDraftCommitMessage(cd.getFullMessage())

        cd.accepted.connect(onAccept)
        cd.rejected.connect(onReject)
        cd.setAttribute(Qt.WA_DeleteOnClose)  # don't leak dialog
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
        cd.setAttribute(Qt.WA_DeleteOnClose)  # don't leak dialog
        cd.show()
        return cd

    # -------------------------------------------------------------------------
    # Push
    # TODO: make async!
    # TODO: REWRITE FOR PYGIT2!!!

    def pushFlow(self, branchName: str = None):
        repo = self.state.repo

        if not branchName:
            branchName = repo.active_branch.name

        branch = repo.heads[branchName]
        tracking = branch.tracking_branch()

        if not tracking:
            QMessageBox.warning(
                self.parentWidget,
                "Cannot Push a Non-Remote-Tracking Branch",
                F"""Can’t push local branch <b>{labelQuote(branch.name)}</b>
                because it isn’t tracking any remote branch.
                <br><br>To set a remote branch to track, right-click on
                local branch {labelQuote(branch.name)} in the sidebar,
                and pick “Tracking”.""")
            return

        remote = repo.remote(tracking.remote_name)
        urls = list(remote.urls)

        qmb = QMessageBox(self)
        qmb.setWindowTitle(F"Push “{branchName}”")
        qmb.setIcon(QMessageBox.Question)
        qmb.setText(F"""Confirm Push?<br>
            <br>Branch: <b>“{branch.name}”</b>
            <br>Tracking: <b>“{tracking.name}”</b>
            <br>Will be pushed to remote: <b>{'; '.join(urls)}</b>""")
        qmb.addButton("Push", QMessageBox.AcceptRole)
        qmb.addButton("Cancel", QMessageBox.RejectRole)
        qmb.accepted.connect(lambda: self.doPush(branchName))
        qmb.setAttribute(Qt.WA_DeleteOnClose)  # don't leak dialog
        qmb.show()

    def doPush(self, branchName: str):
        progress = RemoteProgressDialog(self.parentWidget, "Push in progress")
        pushInfos: list[git.PushInfo]

        PUSHINFO_FAILFLAGS = git.PushInfo.REJECTED | git.PushInfo.REMOTE_FAILURE | git.PushInfo.ERROR

        try:
            pushInfos = remote.put(refspec=branchName, progress=progress)
        except BaseException as e:
            progress.close()
            excMessageBox(e, "Push", "An error occurred while pushing.", parent=self.parentWidget)
            return

        progress.close()

        if len(pushInfos) == 0:
            QMessageBox.critical(self.parentWidget, "Push", "The push operation failed without a result.")
            return

        failed = False
        report = ""
        for info in pushInfos:
            if 0 != (info.flags & PUSHINFO_FAILFLAGS):
                failed = True
            report += F"{info.remote_ref_string}: {info.summary.strip()}\n"
            print(F"push info: {info}, summary: {info.summary.strip()}, local ref: {info.local_ref}; remote ref: {info.remote_ref_string}")

        report = report.rstrip()
        if failed:
            report = "Push failed.\n\n" + report
            QMessageBox.warning(self.parentWidget, "Push failed", report)
        else:
            self.quickRefresh()
            report = "Push successful!\n\n" + report
            QMessageBox.information(self.parentWidget, "Push successful", report)
