# -----------------------------------------------------------------------------
# Copyright (C) 2024 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

import logging

from gitfourchette.forms.brandeddialog import convertToBrandedDialog
from gitfourchette.forms.ui_pushdialog import Ui_PushDialog
from gitfourchette.porcelain import *
from gitfourchette.qt import *
from gitfourchette.toolbox import *

logger = logging.getLogger(__name__)


class ERemoteItem(enum.Enum):
    ExistingRef = enum.auto()
    NewRef = enum.auto()


class PushDialog(QDialog):
    def onPickLocalBranch(self, index: int):
        localBranch = self.currentLocalBranch

        if localBranch.upstream:
            self.ui.trackingLabel.setText(self.tr("tracking {0}").format(lquo(localBranch.upstream.shorthand)))
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
        remoteItem, remoteName = self.ui.remoteBranchEdit.currentData()
        remoteTooltip = self.ui.remoteBranchEdit.itemData(index, Qt.ItemDataRole.ToolTipRole)

        if remoteItem != ERemoteItem.ExistingRef:
            remoteBranchName = withUniqueSuffix(self.currentLocalBranchName, self.reservedRemoteBranchNames[remoteName])
            self.ui.remoteNameLabel.setText("\u21AA " + remoteName + "/")
            self.ui.remoteNameLabel.setToolTip(remoteTooltip)
            self.ui.newRemoteBranchStackedWidget.setCurrentIndex(0)
            self.ui.newRemoteBranchNameEdit.setText(remoteBranchName)
            self.ui.newRemoteBranchNameEdit.setFocus(Qt.FocusReason.TabFocusReason)
        else:
            self.ui.newRemoteBranchStackedWidget.setCurrentIndex(1)
            self.ui.remoteBranchEdit.setFocus(Qt.FocusReason.TabFocusReason)

        self.ui.remoteBranchEdit.setToolTip(remoteTooltip)
        self.updateTrackCheckBox()

        self.remoteBranchNameValidator.run()

    def updateTrackCheckBox(self, resetCheckedState=True):
        localBranch = self.currentLocalBranch
        lbName = localBranch.shorthand
        rbName = self.currentRemoteBranchFullName
        lbUpstream = localBranch.upstream.shorthand if localBranch.upstream else "???"

        lbName = hquoe(lbName)
        rbName = hquoe(rbName)
        lbUpstream = hquoe(lbUpstream)

        hasUpstream = bool(localBranch.upstream)
        isTrackingHomeBranch = hasUpstream and localBranch.upstream.shorthand == self.currentRemoteBranchFullName

        if not resetCheckedState:
            willTrack = self.ui.trackCheckBox.isChecked()
        else:
            willTrack = self.willPushToNewBranch or isTrackingHomeBranch

        if not hasUpstream and willTrack:
            text = self.tr("{0} will track {1}.").format(lbName, rbName)
        elif not hasUpstream and not willTrack:
            text = self.tr("{0} currently does not track any remote branch.").format(lbName)
        elif isTrackingHomeBranch:
            text = self.tr("{0} already tracks remote branch {1}.").format(lbName, lbUpstream)
        elif willTrack:
            text = self.tr("{0} will track {1} instead of {2}.").format(lbName, rbName, lbUpstream)
        else:
            text = self.tr("{0} currently tracks {1}.").format(lbName, lbUpstream)

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
    def currentLocalBranch(self) -> Branch:
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
            rbr: Branch = remoteData
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
            rbr: Branch = remoteData
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
            rbr: Branch = remoteData
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

            for remoteName, remoteBranches in self.repo.listall_remote_branches().items():
                remoteUrl = self.repo.remotes[remoteName].url

                if not firstRemote:
                    comboBox.insertSeparator(comboBox.count())

                for remoteBranch in remoteBranches:
                    identifier = F"{remoteName}/{remoteBranch}"
                    br = self.repo.branches.remote[identifier]
                    font = None

                    if br == self.currentLocalBranch.upstream:
                        caption = F"{identifier} " + self.tr("[tracked]")
                        self.trackedBranchIndex = comboBox.count()
                        icon = stockIcon("vcs-branch")
                        font = QFont()
                        font.setBold(True)
                    else:
                        icon = stockIcon("vcs-branch")
                        caption = identifier

                    payload = (ERemoteItem.ExistingRef, br)

                    comboBox.addItem(icon, caption, payload)

                    if font:
                        comboBox.setItemData(comboBox.count()-1, font, Qt.ItemDataRole.FontRole)
                    comboBox.setItemData(comboBox.count()-1, remoteUrl, Qt.ItemDataRole.ToolTipRole)

                if firstRemote:
                    self.fallbackAutoNewIndex = comboBox.count()
                comboBox.addItem(
                    stockIcon("SP_FileDialogNewFolder"),
                    self.tr("New remote branch on {0}").format(lquo(remoteName)),
                    (ERemoteItem.NewRef, remoteName))
                comboBox.setItemData(comboBox.count()-1, remoteUrl, Qt.ItemDataRole.ToolTipRole)

                firstRemote = False

    def __init__(self, repo: Repo, branch: Branch, parent: QWidget):
        super().__init__(parent)
        self.repo = repo
        self.reservedRemoteBranchNames = self.repo.listall_remote_branches()

        self.fallbackAutoNewIndex = 0
        self.trackedBranchIndex = -1
        self.pushInProgress = False

        self.ui = Ui_PushDialog()
        self.ui.setupUi(self)
        self.ui.trackingLabel.setMinimumHeight(self.ui.trackingLabel.height())
        self.ui.trackingLabel.setMaximumHeight(self.ui.trackingLabel.height())

        self.startOperationButton: QPushButton = self.ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok)
        self.startOperationButton.setText(self.tr("&Push"))
        self.startOperationButton.setIcon(stockIcon("git-push"))

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

        self.setWindowModality(Qt.WindowModality.WindowModal)

    def setOkButtonText(self):
        icon = "git-push"
        tip = ""

        if self.willForcePush:
            text = self.tr("Force &push")
            icon = "achtung"
            tip = self.tr("Force push: Destructive action!")
        elif self.willPushToNewBranch:
            text = self.tr("&Push new branch")
        else:
            text = self.tr("&Push")

        okButton: QPushButton = self.ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok)
        okButton.setText(text)
        okButton.setIcon(stockIcon(icon))
        okButton.setToolTip(tip)

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
            for w, enableW in zip(widgets, self.enableInputsBackup, strict=True):
                w.setEnabled(enableW)

    def reject(self):
        if self.pushInProgress:
            self.remoteLink.raiseAbortFlag()
        else:
            super().reject()
