from gitfourchette import settings
from gitfourchette.qt import *
from gitfourchette.remotelink import RemoteLink
from gitfourchette.widgets.brandeddialog import convertToBrandedDialog
from gitfourchette.widgets.ui_clonedialog import Ui_CloneDialog
from gitfourchette.workqueue import WorkQueue
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
            self.ui.urlEdit.addItem("Clear history", "CLEAR")
        self.ui.urlEdit.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)

    def onComboBoxItemActivated(self, index):
        itemData = self.ui.urlEdit.itemData(index, Qt.UserRole)
        if itemData == "CLEAR":  # clear history
            settings.history.clearCloneHistory()
            self.initUrlComboBox()

    def __init__(self, initialUrl: str, parent: QWidget):
        super().__init__(parent)

        self.cloneInProgress = False
        self.remoteLink = None

        self.ui = Ui_CloneDialog()
        self.ui.setupUi(self)

        self.initUrlComboBox()
        self.ui.urlEdit.activated.connect(self.onComboBoxItemActivated)

        self.ui.browseButton.setIcon(self.style().standardIcon(QStyle.SP_DialogOpenButton))
        self.ui.browseButton.clicked.connect(self.browse)

        self.cloneButton: QPushButton = self.ui.buttonBox.button(QDialogButtonBox.Ok)
        self.cloneButton.setText("C&lone")
        self.cloneButton.setIcon(QIcon.fromTheme("download"))
        self.cloneButton.clicked.connect(self.onCloneClicked)

        self.cancelButton: QPushButton = self.ui.buttonBox.button(QDialogButtonBox.Cancel)
        self.cancelButton.setAutoDefault(False)

        self.ui.statusForm.setBlurb("Hit “Clone” when ready.")

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

        path, _ = QFileDialog.getSaveFileName(self, "Clone repository into", projectName)
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

        link = RemoteLink()
        self.remoteLink = link

        self.ui.statusForm.initProgress(F"Contacting remote host...")
        link.signals.message.connect(self.ui.statusForm.setProgressMessage)
        link.signals.progress.connect(self.ui.statusForm.setProgressValue)

        def work():
            pygit2.clone_repository(url, path, callbacks=link)

        def then(_):
            self.cloneInProgress = False
            settings.history.addCloneUrl(url)
            self.cloneSuccessful.emit(path)
            self.accept()

        def onError(exc: BaseException):
            QApplication.beep()
            QApplication.alert(self, 500)
            self.cloneInProgress = False
            self.enableInputs(True)
            self.ui.statusForm.setBlurb(F"<b>{type(exc).__name__}:</b> {escape(str(exc))}")

        wq = WorkQueue(self)
        wq.put(work, then, "Cloning", errorCallback=onError)
