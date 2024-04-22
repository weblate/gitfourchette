import traceback

from gitfourchette import settings
from gitfourchette.qt import *
from gitfourchette.remotelink import RemoteLink
from gitfourchette.toolbox import *
from gitfourchette.forms.brandeddialog import convertToBrandedDialog
from gitfourchette.forms.ui_clonedialog import Ui_CloneDialog
from gitfourchette.tasks import RepoTask, RepoTaskRunner
import pygit2


class CloneDialog(QDialog):
    cloneSuccessful = Signal(str)
    aboutToReject = Signal()

    def initUrlComboBox(self):
        self.ui.urlEdit.clear()
        self.ui.urlEdit.addItem("")
        if settings.history.cloneHistory:
            self.ui.urlEdit.insertSeparator(self.ui.urlEdit.count())
            for url in settings.history.cloneHistory:
                self.ui.urlEdit.addItem(url)
            self.ui.urlEdit.insertSeparator(self.ui.urlEdit.count())
            self.ui.urlEdit.addItem(stockIcon("edit-clear-history"), self.tr("Clear history"), "CLEAR")
        self.ui.urlEdit.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)

    def onComboBoxItemActivated(self, index):
        itemData = self.ui.urlEdit.itemData(index, Qt.ItemDataRole.UserRole)
        if itemData == "CLEAR":  # clear history
            settings.history.clearCloneHistory()
            settings.history.write()
            self.initUrlComboBox()

    def __init__(self, initialUrl: str, parent: QWidget):
        super().__init__(parent)

        self.remoteLink = None
        self.taskRunner = RepoTaskRunner(self)

        self.ui = Ui_CloneDialog()
        self.ui.setupUi(self)

        self.initUrlComboBox()
        self.ui.urlEdit.activated.connect(self.onComboBoxItemActivated)

        self.ui.browseButton.setIcon(stockIcon(QStyle.StandardPixmap.SP_DialogOpenButton))
        self.ui.browseButton.clicked.connect(self.browse)

        self.cloneButton: QPushButton = self.ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok)
        self.cloneButton.setText(self.tr("C&lone"))
        self.cloneButton.setIcon(QIcon.fromTheme("download"))
        self.cloneButton.clicked.connect(self.onCloneClicked)

        self.cancelButton: QPushButton = self.ui.buttonBox.button(QDialogButtonBox.StandardButton.Cancel)
        self.cancelButton.setAutoDefault(False)

        self.ui.statusForm.setBlurb(self.tr("Hit “Clone” when ready."))

        self.ui.urlEdit.setCurrentText(initialUrl)

        convertToBrandedDialog(self)

        self.ui.urlEdit.setFocus()

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
        for widget in [self.ui.urlLabel, self.ui.urlEdit,
                       self.ui.pathLabel, self.ui.pathEdit,
                       self.ui.browseButton,
                       self.cloneButton]:
            widget.setEnabled(enable)

    def onCloneClicked(self):
        self.taskRunner.put(CloneTask(self), self.url, self.path)


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

    def flow(self, url: str, path: str):
        dialog = self.cloneDialog
        dialog.enableInputs(False)
        dialog.aboutToReject.connect(self.remoteLink.raiseAbortFlag)

        yield from self.flowEnterWorkerThread()
        self.remoteLink.discoverKeyFiles(url)
        pygit2.clone_repository(url, path, callbacks=self.remoteLink)
        self.remoteLink.rememberSuccessfulKeyFile()

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
        dialog.ui.statusForm.setBlurb(F"<b>{type(exc).__name__}:</b> {escape(str(exc))}")
