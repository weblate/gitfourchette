from gitfourchette import settings
from gitfourchette import tasks
from gitfourchette.qt import *
from gitfourchette.remotelink import RemoteLink
from gitfourchette.util import PersistentFileDialog
from gitfourchette.util import stockIcon
from gitfourchette.widgets.brandeddialog import convertToBrandedDialog
from gitfourchette.widgets.ui_clonedialog import Ui_CloneDialog
from gitfourchette.tasks import RepoTaskRunner
from html import escape
import pygit2


class CloneDialog(QDialog):
    cloneSuccessful = Signal(str)

    def initUrlComboBox(self):
        self.ui.urlEdit.clear()
        self.ui.urlEdit.addItem("")
        if settings.history.cloneHistory:
            self.ui.urlEdit.insertSeparator(self.ui.urlEdit.count())
            for url in settings.history.cloneHistory:
                self.ui.urlEdit.addItem(url)
            self.ui.urlEdit.insertSeparator(self.ui.urlEdit.count())
            self.ui.urlEdit.addItem(self.tr("Clear history"), "CLEAR")
        self.ui.urlEdit.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)

    def onComboBoxItemActivated(self, index):
        itemData = self.ui.urlEdit.itemData(index, Qt.ItemDataRole.UserRole)
        if itemData == "CLEAR":  # clear history
            settings.history.clearCloneHistory()
            settings.history.write()
            self.initUrlComboBox()

    def __init__(self, initialUrl: str, parent: QWidget):
        super().__init__(parent)

        self.cloneInProgress = False
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
        #self.setMaximumHeight(self.height())

    def reject(self):
        if self.cloneInProgress:
            self.remoteLink.raiseAbortFlag()
        else:
            super().reject()

    @property
    def url(self):
        return self.ui.urlEdit.currentText()

    @property
    def path(self):
        return self.ui.pathEdit.text()

    def browse(self):
        projectName = self.url.rsplit("/", 1)[-1].removesuffix(".git")

        path, _ = PersistentFileDialog.getSaveFileName(self, "NewRepo",
                                                       self.tr("Clone repository into"), projectName)
        if path:
            self.ui.pathEdit.setText(path)

    def enableInputs(self, enable):
        for widget in [self.ui.urlLabel, self.ui.urlEdit,
                       self.ui.pathLabel, self.ui.pathEdit,
                       self.ui.browseButton,
                       self.cloneButton]:
            widget.setEnabled(enable)

    def onCloneClicked(self):
        self.enableInputs(False)

        url = self.url
        path = self.path

        self.cloneInProgress = True

        link = RemoteLink(self)
        self.remoteLink = link

        self.ui.statusForm.initProgress(self.tr("Contacting remote host..."))
        link.message.connect(self.ui.statusForm.setProgressMessage)
        link.progress.connect(self.ui.statusForm.setProgressValue)

        cloneDialog = self

        class CloneTask(tasks.RepoTask):
            def name(self):
                return translate("Operation", "Clone repository")

            def flow(self):
                yield from self._flowBeginWorkerThread()
                link.discoverKeyFiles()
                pygit2.clone_repository(url, path, callbacks=link)

                yield from self._flowExitWorkerThread()
                cloneDialog.cloneInProgress = False
                settings.history.addCloneUrl(url)
                settings.history.write()
                cloneDialog.cloneSuccessful.emit(path)
                cloneDialog.accept()

            def onError(self, exc: BaseException):
                QApplication.beep()
                QApplication.alert(cloneDialog, 500)
                cloneDialog.cloneInProgress = False
                cloneDialog.enableInputs(True)
                cloneDialog.ui.statusForm.setBlurb(F"<b>{type(exc).__name__}:</b> {escape(str(exc))}")

        self.taskRunner.put(CloneTask(self))
