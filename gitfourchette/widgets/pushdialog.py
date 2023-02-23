from gitfourchette import log
from gitfourchette import porcelain
from gitfourchette import tasks
from gitfourchette.qt import *
from gitfourchette.remotelink import RemoteLink
from gitfourchette.util import paragraphs, QSignalBlockerContext
from gitfourchette.util import addComboBoxItem, stockIcon, escamp, setWindowModal, showWarning
from gitfourchette.widgets.brandeddialog import convertToBrandedDialog
from gitfourchette.widgets.ui_pushdialog import Ui_PushDialog
from html import escape
import enum
import pygit2


class ERemoteItem(enum.Enum):
    ExistingRef = enum.auto()
    NewRef = enum.auto()


class PushDialog(QDialog):
    @staticmethod
    def startPushFlow(parent, repo: pygit2.Repository, repoTaskRunner: tasks.RepoTaskRunner, branchName: str = ""):
        if len(repo.remotes) == 0:
            text = paragraphs(
                translate("PushDialog", "To push a local branch to a remote, you must first add a remote to your repo."),
                translate("PushDialog", "You can do so via “Repo &rarr; Add Remote”."))
            showWarning(parent, translate("PushDialog", "No remotes tracked by this repository"), text)
            return

        if not branchName:
            branchName = porcelain.getActiveBranchShorthand(repo)

        try:
            branch = repo.branches.local[branchName]
        except KeyError:
            showWarning(parent, translate("PushDialog", "No branch to push"),
                        translate("PushDialog", "To push, you must be on a local branch. Try switching to a local branch first."))
            return

        dlg = PushDialog(repo, repoTaskRunner, branch, parent)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        #dlg.accepted.connect(self.pushComplete)
        dlg.show()
        return dlg

    def onPickLocalBranch(self, index: int):
        localBranch = self.currentLocalBranch

        if localBranch.upstream:
            self.ui.trackingLabel.setText(self.tr("tracking “{0}”").format(escamp(localBranch.upstream.shorthand)))
        else:
            self.ui.trackingLabel.setText(self.tr("non-tracking"))

        remoteIndex = self.trackedBranchIndex
        if self.trackedBranchIndex < 0:
            remoteIndex = self.fallbackAutoNewIndex
        self.ui.remoteBranchEdit.setCurrentIndex(remoteIndex)
        self.onPickRemoteBranch(remoteIndex)

        self.updateTrackCheckBox()

    def onPickRemoteBranch(self, index: int):
        localBranch = self.currentLocalBranch

        remoteItem, remoteData = self.ui.remoteBranchEdit.currentData()

        if remoteItem != ERemoteItem.ExistingRef:
            newRBN = porcelain.generateUniqueBranchNameOnRemote(self.repo, remoteData, localBranch.branch_name)
            self.ui.remoteBranchOptionsStack.setCurrentWidget(self.ui.remoteBranchOptionsNameEditPage)
            self.ui.customRemoteBranchNameEdit.setText(newRBN)
            self.ui.customRemoteBranchNameEdit.setFocus(Qt.TabFocusReason)
        else:
            self.ui.remoteBranchOptionsStack.setCurrentWidget(self.ui.remoteBranchOptionsBlankPage)

        self.updateTrackCheckBox()

    def updateTrackCheckBox(self, resetCheckedState=True):
        localBranch = self.currentLocalBranch
        localName = localBranch.shorthand
        remoteName = self.currentRemoteBranchFullName
        lbUpstream = localBranch.upstream.shorthand if localBranch.upstream else "???"

        if not localBranch.upstream:
            text = self.tr("Make “{0}” trac&k “{1}” from now on").format(escamp(localName), escamp(remoteName))
            checked = False
            enabled = True
        elif localBranch.upstream.shorthand == self.currentRemoteBranchFullName:
            text = self.tr("“{0}” already trac&ks “{1}”").format(escamp(localName), escamp(lbUpstream))
            checked = True
            enabled = False
        else:
            text = self.tr("Make “{0}” trac&k “{1}” from now on,\ninstead of “{2}”").format(escamp(localName), escamp(remoteName), escamp(lbUpstream))
            checked = False
            enabled = True

        self.ui.trackCheckBox.setText(text)
        self.ui.trackCheckBox.setEnabled(enabled)
        if resetCheckedState:
            self.ui.trackCheckBox.setChecked(checked)

    @property
    def currentLocalBranchName(self) -> str:
        return self.ui.localBranchEdit.currentData()

    @property
    def currentLocalBranch(self) -> pygit2.Branch:
        return self.repo.branches.local[self.currentLocalBranchName]

    @property
    def forcePush(self) -> bool:
        remoteItem, _ = self.ui.remoteBranchEdit.currentData()
        return remoteItem == ERemoteItem.ExistingRef and self.ui.forcePushCheckBox.isChecked()

    @property
    def currentRemoteName(self):
        remoteItem, remoteData = self.ui.remoteBranchEdit.currentData()

        if remoteItem == ERemoteItem.ExistingRef:
            rbr: pygit2.Branch = remoteData
            return rbr.remote_name
        elif remoteItem == ERemoteItem.NewRef:
            return remoteData
        else:
            raise NotImplementedError()

    @property
    def currentRemoteBranchName(self) -> str:
        data = self.ui.remoteBranchEdit.currentData()
        if data is None:
            return ""
        remoteItem, remoteData = self.ui.remoteBranchEdit.currentData()

        if remoteItem == ERemoteItem.ExistingRef:
            rbr: pygit2.Branch = remoteData
            return rbr.shorthand.removeprefix(rbr.remote_name + "/")
        elif remoteItem == ERemoteItem.NewRef:
            return self.ui.customRemoteBranchNameEdit.text()
        else:
            raise NotImplementedError()

    @property
    def currentRemoteBranchFullName(self) -> str:
        data = self.ui.remoteBranchEdit.currentData()
        if data is None:
            return ""
        remoteItem, remoteData = self.ui.remoteBranchEdit.currentData()

        if remoteItem == ERemoteItem.ExistingRef:
            rbr: pygit2.Branch = remoteData
            return rbr.shorthand
        elif remoteItem == ERemoteItem.NewRef:
            return remoteData + "/" + self.ui.customRemoteBranchNameEdit.text()
        else:
            raise NotImplementedError()

    @property
    def refspec(self):
        prefix = "+" if self.forcePush else ""
        return F"{prefix}refs/heads/{self.currentLocalBranchName}:refs/heads/{self.currentRemoteBranchName}"

    def fillRemoteComboBox(self):
        self.fallbackAutoNewIndex = 0
        self.trackedBranchIndex = -1
        comboBox = self.ui.remoteBranchEdit

        with QSignalBlockerContext(comboBox):
            comboBox.clear()
            firstRemote = True

            for remoteName, remoteBranches in porcelain.getRemoteBranchNames(self.repo).items():
                if not firstRemote:
                    comboBox.insertSeparator(comboBox.count())

                for remoteBranch in remoteBranches:
                    identifier = F"{remoteName}/{remoteBranch}"
                    br = self.repo.branches.remote[identifier]
                    font = None

                    if br == self.currentLocalBranch.upstream:
                        caption = F"{identifier} " + self.tr("[tracked]")
                        self.trackedBranchIndex = comboBox.count()
                        icon = stockIcon(QStyle.StandardPixmap.SP_DirHomeIcon)
                        font = QFont()
                        font.setBold(True)
                    else:
                        icon = stockIcon("vcs-branch")
                        caption = identifier

                    payload = (ERemoteItem.ExistingRef, br)

                    comboBox.addItem(icon, caption, payload)

                    if font:
                        comboBox.setItemData(comboBox.count()-1, font, Qt.ItemDataRole.FontRole)
                    comboBox.setItemData(comboBox.count()-1, self.repo.remotes[remoteName].url, Qt.ItemDataRole.ToolTipRole)

                if firstRemote:
                    self.fallbackAutoNewIndex = comboBox.count()
                comboBox.addItem(
                    stockIcon(QStyle.StandardPixmap.SP_FileDialogNewFolder),
                    self.tr("New remote branch:") + F" {remoteName}/...",
                    (ERemoteItem.NewRef, remoteName))

                firstRemote = False

    def __init__(self, repo: pygit2.Repository, repoTaskRunner: tasks.RepoTaskRunner, branch: pygit2.Branch, parent: QWidget):
        super().__init__(parent)
        self.repo = repo
        self.repoTaskRunner = repoTaskRunner

        self.fallbackAutoNewIndex = 0
        self.trackedBranchIndex = -1
        self.pushInProgress = False

        self.ui = Ui_PushDialog()
        self.ui.setupUi(self)

        self.startOperationButton: QPushButton = self.ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok)
        self.startOperationButton.setText(self.tr("&Push"))
        self.startOperationButton.setIcon(stockIcon("vcs-push"))
        self.startOperationButton.clicked.connect(self.onPushClicked)

        pickBranchIndex = 0

        for lbName in repo.branches.local:
            i = addComboBoxItem(self.ui.localBranchEdit, lbName, lbName)
            if branch.shorthand == lbName:
                pickBranchIndex = i
        self.ui.localBranchEdit.setCurrentIndex(pickBranchIndex)

        self.ui.localBranchEdit.activated.connect(self.fillRemoteComboBox)
        self.ui.localBranchEdit.activated.connect(self.onPickLocalBranch)
        self.ui.remoteBranchEdit.activated.connect(self.onPickRemoteBranch)
        self.ui.customRemoteBranchNameEdit.textEdited.connect(lambda text: self.updateTrackCheckBox(False))

        # Fire initial activated signal to set up comboboxes
        self.ui.localBranchEdit.activated.emit(pickBranchIndex)

        convertToBrandedDialog(self)

        setWindowModal(self)

    def enableInputs(self, on: bool):
        widgets = [self.ui.remoteBranchEdit,
                   self.ui.localBranchEdit,
                   self.ui.customRemoteBranchNameEdit,
                   self.ui.forcePushCheckBox,
                   self.ui.trackCheckBox,
                   self.startOperationButton]

        if not on:
            # Remember which widgets were disabled already
            self.enableInputsBackup = [w.isEnabled() for w in widgets]
            for w in widgets:
                w.setEnabled(False)
        else:
            for w, enableW in zip(widgets, self.enableInputsBackup):
                w.setEnabled(enableW)

    def onPushClicked(self):
        remote = self.repo.remotes[self.currentRemoteName]
        log.info("PushDialog", self.refspec, remote.name)
        link = RemoteLink(self)
        self.remoteLink = link

        self.ui.statusForm.initProgress(self.tr("Contacting remote host..."))
        link.message.connect(self.ui.statusForm.setProgressMessage)
        link.progress.connect(self.ui.statusForm.setProgressValue)

        if self.ui.trackCheckBox.isEnabled() and self.ui.trackCheckBox.isChecked():
            resetTrackingReference = self.currentRemoteBranchFullName
        else:
            resetTrackingReference = None

        pushDialog = self

        class PushTask(tasks.RepoTask):
            def name(self):
                return translate("Operation", "Push")

            def refreshWhat(self) -> tasks.TaskAffectsWhat:
                return tasks.TaskAffectsWhat.REMOTES

            def flow(self):
                yield from self._flowBeginWorkerThread()
                remote.push([pushDialog.refspec], callbacks=link)
                if resetTrackingReference:
                    porcelain.editTrackingBranch(self.repo, pushDialog.currentLocalBranchName, resetTrackingReference)

                yield from self._flowExitWorkerThread()
                pushDialog.pushInProgress = False
                pushDialog.accept()

            def onError(self, exc: BaseException):
                QApplication.beep()
                QApplication.alert(pushDialog, 500)
                pushDialog.pushInProgress = False
                pushDialog.enableInputs(True)
                pushDialog.ui.statusForm.setBlurb(F"<b>{type(exc).__name__}:</b> {escape(str(exc))}")

        self.pushInProgress = True
        self.enableInputs(False)
        self.repoTaskRunner.put(PushTask(self))

    def reject(self):
        if self.pushInProgress:
            self.remoteLink.raiseAbortFlag()
        else:
            super().reject()
