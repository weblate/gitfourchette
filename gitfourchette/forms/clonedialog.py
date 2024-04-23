import re
import traceback

import pygit2

from gitfourchette import settings
from gitfourchette.forms.brandeddialog import convertToBrandedDialog
from gitfourchette.forms.ui_clonedialog import Ui_CloneDialog
from gitfourchette.qt import *
from gitfourchette.remotelink import RemoteLink
from gitfourchette.tasks import RepoTask, RepoTaskRunner
from gitfourchette.toolbox import *
from gitfourchette.trtables import TrTables


class CloneDialog(QDialog):
    cloneSuccessful = Signal(str)
    aboutToReject = Signal()

    urlEditUserDataClearHistory = "CLEAR_HISTORY"

    def __init__(self, initialUrl: str, parent: QWidget):
        super().__init__(parent)

        self.remoteLink = None
        self.taskRunner = RepoTaskRunner(self)

        self.ui = Ui_CloneDialog()
        self.ui.setupUi(self)

        self.initUrlComboBox()
        self.ui.urlEdit.activated.connect(self.onUrlActivated)

        self.ui.browseButton.setIcon(stockIcon(QStyle.StandardPixmap.SP_DialogOpenButton))
        self.ui.browseButton.clicked.connect(self.browse)

        self.cloneButton: QPushButton = self.ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok)
        self.cloneButton.setText(self.tr("C&lone"))
        self.cloneButton.setIcon(QIcon.fromTheme("download"))
        self.cloneButton.clicked.connect(self.onCloneClicked)

        self.cancelButton: QPushButton = self.ui.buttonBox.button(QDialogButtonBox.StandardButton.Cancel)
        self.cancelButton.setAutoDefault(False)

        self.ui.statusForm.setBlurb(self.tr("Hit “Clone” when ready."))

        self.ui.shallowCloneDepthSpinBox.valueChanged.connect(self.onShallowCloneDepthChanged)
        self.ui.shallowCloneCheckBox.stateChanged.connect(self.onShallowCloneCheckBoxStateChanged)
        self.ui.shallowCloneCheckBox.setMinimumHeight(max(self.ui.shallowCloneCheckBox.height(), self.ui.shallowCloneDepthSpinBox.height()))  # prevent jumping around
        self.onShallowCloneCheckBoxStateChanged(self.ui.shallowCloneCheckBox.checkState())

        convertToBrandedDialog(self)

        self.ui.urlEdit.setCurrentText(initialUrl)
        self.ui.urlEdit.setFocus()

    def initUrlComboBox(self):
        self.ui.urlEdit.clear()
        self.ui.urlEdit.addItem("")
        if settings.history.cloneHistory:
            self.ui.urlEdit.insertSeparator(self.ui.urlEdit.count())
            for url in settings.history.cloneHistory:
                self.ui.urlEdit.addItem(url)
            self.ui.urlEdit.insertSeparator(self.ui.urlEdit.count())
            self.ui.urlEdit.addItem(stockIcon("edit-clear-history"), self.tr("Clear history"), CloneDialog.urlEditUserDataClearHistory)
        self.ui.urlEdit.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)

    def onUrlActivated(self, index: int):
        itemData = self.ui.urlEdit.itemData(index, Qt.ItemDataRole.UserRole)
        if itemData == CloneDialog.urlEditUserDataClearHistory:
            settings.history.clearCloneHistory()
            settings.history.write()
            self.initUrlComboBox()

    def onShallowCloneCheckBoxStateChanged(self, state):
        isChecked = state not in [0, Qt.CheckState.Unchecked]
        if isChecked:
            self.onShallowCloneDepthChanged(self.ui.shallowCloneDepthSpinBox.value())
        else:
            self.ui.shallowCloneCheckBox.setText(self.tr("&Shallow clone"))
        self.ui.shallowCloneDepthSpinBox.setVisible(isChecked)
        self.ui.shallowCloneSuffix.setVisible(isChecked)

    def onShallowCloneDepthChanged(self, depth: int):
        # Re-translate text for correct plural form
        text = self.tr("&Shallow clone: Fetch up to %n commits per branch", "", depth)
        parts = re.split(r"\b\d(?:.*\d)?\b", text, 1)
        assert len(parts) >= 2
        self.ui.shallowCloneCheckBox.setText(parts[0].strip())
        self.ui.shallowCloneSuffix.setText(parts[1].strip())

    def reject(self):
        # Emit "aboutToReject" before destroying the dialog so TaskRunner has time to wrap up.
        self.aboutToReject.emit()
        self.taskRunner.killCurrentTask()
        self.taskRunner.joinZombieTask()
        super().reject()  # destroys the dialog then emits the "rejected" signal

    @property
    def url(self):
        return self.ui.urlEdit.currentText()

    @property
    def path(self):
        return self.ui.pathEdit.text()

    def browse(self):
        projectName = self.url.rsplit("/", 1)[-1].removesuffix(".git")

        qfd = PersistentFileDialog.saveFile(
            self, "NewRepo", self.tr("Clone repository into"), projectName)

        qfd.fileSelected.connect(self.ui.pathEdit.setText)
        qfd.show()

    def enableInputs(self, enable):
        grayable = [
            self.ui.urlLabel,
            self.ui.urlEdit,
            self.ui.pathLabel,
            self.ui.pathEdit,
            self.ui.browseButton,
            self.ui.shallowCloneCheckBox,
            self.ui.shallowCloneDepthSpinBox,
            self.ui.shallowCloneSuffix,
            self.cloneButton
        ]
        for widget in grayable:
            widget.setEnabled(enable)

    def onCloneClicked(self):
        depth = 0

        if self.ui.shallowCloneCheckBox.isChecked():
            depth = self.ui.shallowCloneDepthSpinBox.value()

        self.taskRunner.put(CloneTask(self), url=self.url, path=self.path, depth=depth)


class CloneTask(RepoTask):
    """
    Even though we don't have a Repository yet, this is a RepoTask so we can
    easily run the clone operation in a background thread.
    """

    def __init__(self, dialog: CloneDialog):
        super().__init__(dialog)
        self.cloneDialog = dialog
        self.remoteLink = RemoteLink(self)

        dialog.ui.statusForm.initProgress(self.tr("Contacting remote host..."))
        self.remoteLink.message.connect(dialog.ui.statusForm.setProgressMessage)
        self.remoteLink.progress.connect(dialog.ui.statusForm.setProgressValue)

    def abort(self):
        self.remoteLink.raiseAbortFlag()

    def flow(self, url: str, path: str, depth: int):
        dialog = self.cloneDialog
        dialog.enableInputs(False)
        dialog.aboutToReject.connect(self.remoteLink.raiseAbortFlag)

        yield from self.flowEnterWorkerThread()
        with self.remoteLink.remoteKeyFileContext(url):
            pygit2.clone_repository(url, path, callbacks=self.remoteLink, depth=depth)

        yield from self.flowEnterUiThread()
        settings.history.addCloneUrl(url)
        settings.history.write()
        dialog.cloneSuccessful.emit(path)
        dialog.accept()

    def onError(self, exc: BaseException):
        traceback.print_exception(exc.__class__, exc, exc.__traceback__)
        dialog = self.cloneDialog
        QApplication.beep()
        QApplication.alert(dialog, 500)
        dialog.enableInputs(True)
        dialog.ui.statusForm.setBlurb(f"<span style='white-space: pre;'><b>{TrTables.exceptionName(exc)}:</b> {escape(str(exc))}")
