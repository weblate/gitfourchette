from gitfourchette import log
from gitfourchette import porcelain
from gitfourchette import tasks
from gitfourchette.qt import *
from gitfourchette.remotelink import RemoteLink
from gitfourchette.toolbox import *
from gitfourchette.trtables import TrTables
from gitfourchette.forms.brandeddialog import convertToBrandedDialog
from gitfourchette.forms.ui_pushdialog import Ui_PushDialog
import enum
import pygit2
import traceback


class ERemoteItem(enum.Enum):
    ExistingRef = enum.auto()
    NewRef = enum.auto()


class PushDialog(QDialog):
    @staticmethod
    def startPushFlow(parent, repo: pygit2.Repository, repoTaskRunner: tasks.RepoTaskRunner, branchName: str = ""):
        if len(repo.remotes) == 0:
            text = paragraphs(
                translate("PushDialog", "To push a local branch to a remote, you must first add a remote to your repo."),
                translate("PushDialog", "You can do so via <i>“Repo &rarr; Add Remote”</i>."))
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

        self.remoteBranchNameValidator.run()

    def onPickRemoteBranch(self, index: int):
        localBranch = self.currentLocalBranch

        remoteItem, remoteData = self.ui.remoteBranchEdit.currentData()

        if remoteItem != ERemoteItem.ExistingRef:
            self.ui.remoteNameLabel.setText("\u21AA " + remoteData + "/")
            newRBN = porcelain.generateUniqueBranchNameOnRemote(self.repo, remoteData, localBranch.branch_name)
            self.ui.newRemoteBranchStackedWidget.setCurrentIndex(0)
            self.ui.newRemoteBranchNameEdit.setText(newRBN)
            self.ui.newRemoteBranchNameEdit.setFocus(Qt.FocusReason.TabFocusReason)
        else:
            self.ui.newRemoteBranchStackedWidget.setCurrentIndex(1)
            self.ui.remoteBranchEdit.setFocus(Qt.FocusReason.TabFocusReason)
            pass

        self.updateTrackCheckBox()

        self.remoteBranchNameValidator.run()

    def updateTrackCheckBox(self, resetCheckedState=True):
        localBranch = self.currentLocalBranch
        lbName = localBranch.shorthand
        rbName = self.currentRemoteBranchFullName
        lbUpstream = localBranch.upstream.shorthand if localBranch.upstream else "???"

        metrics = self.ui.trackingLabel.fontMetrics()

        lbName = escape(metrics.elidedText(lbName, Qt.TextElideMode.ElideMiddle, 150))
        rbName = escape(metrics.elidedText(rbName, Qt.TextElideMode.ElideMiddle, 150))
        lbUpstream = escape(metrics.elidedText(lbUpstream, Qt.TextElideMode.ElideMiddle, 150))

        hasUpstream = bool(localBranch.upstream)
        isTrackingHomeBranch = hasUpstream and localBranch.upstream.shorthand == self.currentRemoteBranchFullName

        if not resetCheckedState:
            willTrack = self.ui.trackCheckBox.isChecked()
        else:
            willTrack = self.willPushToNewBranch or isTrackingHomeBranch

        if not hasUpstream and willTrack:
            text = self.tr("“{0}” will track “{1}”.").format(lbName, rbName)
        elif not hasUpstream and not willTrack:
            text = self.tr("“{0}” currently does not track any remote branch.").format(lbName)
        elif isTrackingHomeBranch:
            text = self.tr("“{0}” already tracks remote branch “{1}”.").format(lbName, lbUpstream)
        elif willTrack:
            text = self.tr("“{0}” will track “{1}” instead of “{2}”.").format(lbName, rbName, lbUpstream)
        else:
            text = self.tr("“{0}” currently tracks “{1}”.").format(lbName, lbUpstream)

        self.ui.trackingLabel.setWordWrap(True)
        self.ui.trackingLabel.setText("<small>" + text + "</small>")
        self.ui.trackingLabel.setContentsMargins(20, 0, 0, 0)
        self.ui.trackingLabel.setEnabled(not isTrackingHomeBranch)
        self.ui.trackCheckBox.setEnabled(not isTrackingHomeBranch)
        self.setOkButtonText()

        if resetCheckedState:
            with QSignalBlockerContext(self.ui.trackCheckBox):
                self.ui.trackCheckBox.setChecked(willTrack)

    @property
    def currentLocalBranchName(self) -> str:
        return self.ui.localBranchEdit.currentData()

    @property
    def currentLocalBranch(self) -> pygit2.Branch:
        return self.repo.branches.local[self.currentLocalBranchName]

    @property
    def willForcePush(self) -> bool:
        return not self.willPushToNewBranch and self.ui.forcePushCheckBox.isChecked()

    @property
    def willPushToNewBranch(self) -> bool:
        remoteItem, _ = self.ui.remoteBranchEdit.currentData()
        return remoteItem == ERemoteItem.NewRef

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
            return self.ui.newRemoteBranchNameEdit.text()
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
            return remoteData + "/" + self.ui.newRemoteBranchNameEdit.text()
        else:
            raise NotImplementedError()

    @property
    def refspec(self):
        prefix = "+" if self.willForcePush else ""
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
                        icon = stockIcon("vcs-branch")  # stockIcon(QStyle.StandardPixmap.SP_DirHomeIcon)
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
                    self.tr("New remote branch on {0}").format(escamp(remoteName)),
                    (ERemoteItem.NewRef, remoteName))

                firstRemote = False

    def __init__(self, repo: pygit2.Repository, repoTaskRunner: tasks.RepoTaskRunner, branch: pygit2.Branch, parent: QWidget):
        super().__init__(parent)
        self.repo = repo
        self.repoTaskRunner = repoTaskRunner
        self.reservedRemoteBranchNames = porcelain.getRemoteBranchNames(self.repo)

        self.fallbackAutoNewIndex = 0
        self.trackedBranchIndex = -1
        self.pushInProgress = False

        self.ui = Ui_PushDialog()
        self.ui.setupUi(self)
        self.ui.trackingLabel.setMinimumHeight(self.ui.trackingLabel.height())
        self.ui.trackingLabel.setMaximumHeight(self.ui.trackingLabel.height())

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
        self.ui.newRemoteBranchNameEdit.textEdited.connect(lambda text: self.updateTrackCheckBox(False))
        self.ui.trackCheckBox.toggled.connect(lambda: self.updateTrackCheckBox(False))

        self.remoteBranchNameValidator = ValidatorMultiplexer(self)
        self.remoteBranchNameValidator.setGatedWidgets(self.ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok))
        self.remoteBranchNameValidator.connectInput(self.ui.newRemoteBranchNameEdit, self.validateCustomRemoteBranchName)
        # don't prime the validator!

        # Fire initial activated signal to set up comboboxes
        self.ui.localBranchEdit.activated.emit(pickBranchIndex)

        self.ui.forcePushCheckBox.clicked.connect(self.setOkButtonText)
        self.setOkButtonText()

        convertToBrandedDialog(self)

        setWindowModal(self)

    def setOkButtonText(self):
        okButton = self.ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok)
        if self.willForcePush:
            okButton.setText(self.tr("Force &push"))
        elif self.willPushToNewBranch:
            okButton.setText(self.tr("&Push new branch"))
        else:
            okButton.setText(self.tr("&Push"))

    def validateCustomRemoteBranchName(self, name: str):
        if not self.ui.newRemoteBranchNameEdit.isVisibleTo(self):
            return ""

        reservedNames = self.reservedRemoteBranchNames.get(self.currentRemoteName, [])

        return nameValidationMessage(name, reservedNames,
                                     self.tr("This name is already taken by another branch on this remote."))

    def enableInputs(self, on: bool):
        widgets = [self.ui.remoteBranchEdit,
                   self.ui.localBranchEdit,
                   self.ui.newRemoteBranchNameEdit,
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

            def effects(self) -> tasks.TaskEffects:
                return tasks.TaskEffects.Remotes

            def flow(self):
                yield from self._flowBeginWorkerThread()
                link.discoverKeyFiles(remote)
                remote.push([pushDialog.refspec], callbacks=link)
                if resetTrackingReference:
                    porcelain.editTrackingBranch(self.repo, pushDialog.currentLocalBranchName, resetTrackingReference)

                yield from self._flowExitWorkerThread()
                pushDialog.pushInProgress = False
                pushDialog.accept()

            def onError(self, exc: BaseException):
                traceback.print_exception(exc)
                QApplication.beep()
                QApplication.alert(pushDialog, 500)
                pushDialog.pushInProgress = False
                pushDialog.enableInputs(True)
                pushDialog.ui.statusForm.setBlurb(F"<b>{TrTables.exceptionName(exc)}:</b> {escape(str(exc))}")

        self.pushInProgress = True
        self.enableInputs(False)

        task = PushTask(self)
        task.setRepo(self.repo)
        self.repoTaskRunner.put(task)

    def reject(self):
        if self.pushInProgress:
            self.remoteLink.raiseAbortFlag()
        else:
            super().reject()
