import re
import traceback
import urllib.parse
from contextlib import suppress
from pathlib import Path

import pygit2
from pygit2.enums import RepositoryOpenFlag

from gitfourchette import repoconfig
from gitfourchette import settings
from gitfourchette.forms.brandeddialog import convertToBrandedDialog
from gitfourchette.forms.ui_clonedialog import Ui_CloneDialog
from gitfourchette.porcelain import Repo
from gitfourchette.qt import *
from gitfourchette.remotelink import RemoteLink
from gitfourchette.tasks import RepoTask, RepoTaskRunner
from gitfourchette.toolbox import *
from gitfourchette.trtables import TrTables


def _projectNameFromUrl(url: str) -> str:
    name = url.rsplit("/", 1)[-1].removesuffix(".git")
    name = urllib.parse.unquote(name)
    # Sanitize name
    for c in " ?/\\*~<>|:":
        name = name.replace(c, "_")
    return name


class CloneDialog(QDialog):
    cloneSuccessful = Signal(str)
    aboutToReject = Signal()

    urlEditUserDataClearHistory = "CLEAR_HISTORY"

    def __init__(self, initialUrl: str, parent: QWidget):
        super().__init__(parent)

        if not initialUrl:
            initialUrl = guessRemoteUrlFromText(QApplication.clipboard().text())

        self.remoteLink = None
        self.taskRunner = RepoTaskRunner(self)

        self.ui = Ui_CloneDialog()
        self.ui.setupUi(self)

        self.initUrlComboBox()
        self.ui.urlEdit.activated.connect(self.onUrlActivated)

        self.ui.browseButton.setIcon(stockIcon("SP_DialogOpenButton"))
        self.ui.browseButton.clicked.connect(self.browse)

        self.setDefaultCloneLocationAction = QAction("(SET)")
        self.setDefaultCloneLocationAction.triggered.connect(lambda: self.setDefaultCloneLocationPref(self.pathParentDir))
        self.clearDefaultCloneLocationAction = QAction(stockIcon("edit-clear-history"), self.tr("Reset default clone location"))
        self.clearDefaultCloneLocationAction.triggered.connect(lambda: self.setDefaultCloneLocationPref(""))
        self.ui.browseButton.setMenu(ActionDef.makeQMenu(
            self.ui.browseButton, [self.setDefaultCloneLocationAction, self.clearDefaultCloneLocationAction]))
        self.updateDefaultCloneLocationAction()  # prime default clone path actions
        self.ui.pathEdit.textChanged.connect(self.updateDefaultCloneLocationAction)

        self.cloneButton: QPushButton = self.ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok)
        self.cloneButton.setText(self.tr("C&lone"))
        self.cloneButton.setIcon(QIcon.fromTheme("download"))
        self.cloneButton.clicked.connect(self.onCloneClicked)

        self.cancelButton: QPushButton = self.ui.buttonBox.button(QDialogButtonBox.StandardButton.Cancel)
        self.cancelButton.setAutoDefault(False)

        self.ui.statusForm.setBlurb(self.tr("Hit {0} when ready.").format(tquo(self.cloneButton.text().replace("&", ""))))

        self.ui.shallowCloneDepthSpinBox.valueChanged.connect(self.onShallowCloneDepthChanged)
        self.ui.shallowCloneCheckBox.stateChanged.connect(self.onShallowCloneCheckBoxStateChanged)
        self.ui.shallowCloneCheckBox.setMinimumHeight(max(self.ui.shallowCloneCheckBox.height(), self.ui.shallowCloneDepthSpinBox.height()))  # prevent jumping around
        self.onShallowCloneCheckBoxStateChanged(self.ui.shallowCloneCheckBox.checkState())

        convertToBrandedDialog(self)

        self.ui.urlEdit.editTextChanged.connect(self.autoFillDownloadPath)
        self.ui.urlEdit.setCurrentText(initialUrl)
        self.ui.urlEdit.setFocus()

        validator = ValidatorMultiplexer(self)
        validator.setGatedWidgets(self.cloneButton)
        validator.connectInput(self.ui.urlEdit.lineEdit(), self.validateUrl)
        validator.connectInput(self.ui.pathEdit, self.validatePath)
        validator.run(silenceEmptyWarnings=True)

    def validateUrl(self, url):
        if not url:
            return translate("NameValidationError", "Please fill in this field.")
        return ""

    def validatePath(self, path):
        if not path:
            # Avoid wording this as "cannot be empty" to prevent confusion with "directory not empty".
            return translate("NameValidationError", "Please fill in this field.")
        path = Path(path)
        if not path.is_absolute():
            return translate("NameValidationError", "Please enter an absolute path.")
        if path.is_file():
            return translate("NameValidationError", "There’s already a file at this path.")
        if path.is_dir():
            with suppress(StopIteration):
                next(path.iterdir())  # raises StopIteration if directory is not empty
                return translate("NameValidationError", "This directory isn’t empty.")
        return ""

    def autoFillDownloadPath(self, url):
        # Get standard download location
        downloadPath = Path(settings.prefs.resolveDefaultCloneLocation())

        # Don't overwrite if user has set a custom path
        currentPath = self.ui.pathEdit.text()
        if currentPath and Path(currentPath).parent != downloadPath:
            return

        # Extract project name; clear target path if blank
        projectName = _projectNameFromUrl(url)
        if not projectName or projectName in [".", ".."]:
            self.ui.pathEdit.setText("")
            return

        # Append differentiating number if this path already exists
        projectName = withUniqueSuffix(projectName, lambda x: (downloadPath / x).exists())

        # Set target path to <downloadPath>/<projectName>
        target = downloadPath / projectName
        assert not target.exists()

        self.ui.pathEdit.setText(str(target))

    def updateDefaultCloneLocationAction(self):
        self.clearDefaultCloneLocationAction.setEnabled(settings.prefs.defaultCloneLocation != "")

        location = self.pathParentDir
        action = self.setDefaultCloneLocationAction

        if self.validatePath(self.path):  # truthy if validation error
            action.setText(self.tr("Set current location as default clone location"))
            action.setEnabled(False)
            return

        display = lquoe(compactPath(location))
        if location == settings.prefs.resolveDefaultCloneLocation():
            action.setEnabled(False)
            action.setText(self.tr("{0} is the default clone location").format(display))
        else:
            action.setEnabled(True)
            action.setText(self.tr("Set {0} as default clone location").format(display))

    def setDefaultCloneLocationPref(self, location: str):
        settings.prefs.defaultCloneLocation = location
        settings.prefs.setDirty()
        self.updateDefaultCloneLocationAction()

    def initUrlComboBox(self):
        urlEdit = self.ui.urlEdit
        urlEdit.clear()

        if settings.history.cloneHistory:
            for url in settings.history.cloneHistory:
                urlEdit.addItem(url)
            urlEdit.insertSeparator(urlEdit.count())

        urlEdit.addItem(stockIcon("edit-clear-history"), self.tr("Clear history"), CloneDialog.urlEditUserDataClearHistory)

        # "Clear history" is added even if the history is empty, so that the
        # QComboBox's arrow button - which cannot be hidden - still pops up
        # something when clicked, as the user might expect.
        if not settings.history.cloneHistory:
            clearItem: QStandardItem = urlEdit.model().item(urlEdit.count()-1)
            clearItem.setFlags(clearItem.flags() & ~Qt.ItemFlag.ItemIsEnabled)

        self.ui.urlEdit.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)

    def onUrlActivated(self, index: int):
        itemData = self.ui.urlEdit.itemData(index, Qt.ItemDataRole.UserRole)
        if itemData == CloneDialog.urlEditUserDataClearHistory:
            settings.history.clearCloneHistory()
            settings.history.write()
            self.initUrlComboBox()

    @DisableWidgetUpdatesContext.methodDecorator
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

    @property
    def pathParentDir(self):
        return str(Path(self.path).parent)

    def browse(self):
        existingPath = Path(self.path) if self.path else None

        if existingPath:
            initialName = existingPath.name
        else:
            initialName = _projectNameFromUrl(self.url)

        qfd = PersistentFileDialog.saveFile(self, "NewRepo", self.tr("Clone repository into"), initialName)

        # Rationale for omitting directory-related options that appear to make sense at first glance:
        # - FileMode.Directory: forces user to hit "new folder" to enter the name of the repo
        # - Options.ShowDirsOnly: KDE Plasma 6's native dialog forces user to hit "new folder" when this flag is set
        qfd.setOption(QFileDialog.Option.DontConfirmOverwrite, True)  # we'll show our own warning if the file already exists
        qfd.setOption(QFileDialog.Option.HideNameFilterDetails, True)  # not sure Qt honors this...

        qfd.setLabelText(QFileDialog.DialogLabel.FileName, self.ui.pathLabel.text())  # "Clone into:"
        qfd.setLabelText(QFileDialog.DialogLabel.Accept, self.tr("Clone here"))

        if existingPath:
            qfd.setDirectory(str(existingPath.parent))

        qfd.fileSelected.connect(self.ui.pathEdit.setText)
        qfd.show()

    def enableInputs(self, enable):
        grayable = [
            self.ui.urlLabel,
            self.ui.urlEdit,
            self.ui.pathLabel,
            self.ui.pathEdit,
            self.ui.browseButton,
            self.ui.optionsLabel,
            self.ui.recurseSubmodulesCheckBox,
            self.ui.shallowCloneCheckBox,
            self.ui.shallowCloneDepthSpinBox,
            self.ui.shallowCloneSuffix,
            self.ui.keyFilePicker,
            self.cloneButton
        ]
        for widget in grayable:
            widget.setEnabled(enable)

    def onCloneClicked(self):
        depth = 0
        privKeyPath = self.ui.keyFilePicker.privateKeyPath()
        recursive = self.ui.recurseSubmodulesCheckBox.isChecked()

        if self.ui.shallowCloneCheckBox.isChecked():
            depth = self.ui.shallowCloneDepthSpinBox.value()

        self.ui.statusForm.initProgress(self.tr("Contacting remote host..."))
        self.taskRunner.put(CloneTask(self), url=self.url, path=self.path, depth=depth, privKeyPath=privKeyPath, recursive=recursive)


class CloneTask(RepoTask):
    """
    Even though we don't have a Repository yet, this is a RepoTask so we can
    easily run the clone operation in a background thread.
    """

    stickyStatus = Signal(str)

    def __init__(self, dialog: CloneDialog):
        super().__init__(dialog)
        self.cloneDialog = dialog
        self.remoteLink = RemoteLink(self)
        self.remoteLink.message.connect(dialog.ui.statusForm.setProgressMessage)
        self.remoteLink.progress.connect(dialog.ui.statusForm.setProgressValue)
        self.stickyStatus.connect(dialog.ui.statusGroupBox.setTitle)

    def abort(self):
        self.remoteLink.raiseAbortFlag()

    def flow(self, url: str, path: str, depth: int, privKeyPath: str, recursive: bool):
        dialog = self.cloneDialog
        dialog.enableInputs(False)
        dialog.aboutToReject.connect(self.remoteLink.raiseAbortFlag)

        # Enter worker thread
        yield from self.flowEnterWorkerThread()

        # Set private key
        if privKeyPath:
            self.remoteLink.forceCustomKeyFile(privKeyPath)

        # Clone the repo
        self.stickyStatus.emit(self.tr("Cloning..."))
        with self.remoteLink.remoteKeyFileContext(url):
            clonedRepo = pygit2.clone_repository(url, path, callbacks=self.remoteLink, depth=depth)
        clonedRepo = Repo(clonedRepo.workdir, RepositoryOpenFlag.NO_SEARCH)
        self.setRepo(clonedRepo)

        # Store custom key (if any) in cloned repo config
        if privKeyPath:
            repoconfig.setRemoteKeyFile(clonedRepo, clonedRepo.remotes[0].name, privKeyPath)

        # Recurse into submodules
        if recursive:
            yield from self.recurseIntoSubmodules()

        # Done, back to UI thread
        yield from self.flowEnterUiThread()
        settings.history.addCloneUrl(url)
        settings.history.setDirty()
        dialog.cloneSuccessful.emit(path)
        dialog.accept()

    def recurseIntoSubmodules(self):
        # TODO: pygit2.Submodule has several shortcomings here:
        # - Submodule.url crashes if libgit2 returns NULL (see also UpdateSubmodule in nettasks.py)
        # - Submodule.update should let us do a shallow clone since libgit2 allows it (via git_fetch_options)
        # - Submodule.open is broken (that's why we recreate a Repo)

        def frontierGenerator(r: Repo):
            return ((r.submodules[name], path) for name, path in r.listall_submodules_dict(absolute_paths=True).items())

        frontier = list(frontierGenerator(self.repo))

        i = 0
        while frontier:
            i += 1
            submodule, path = frontier.pop(0)

            displayPath = path.removeprefix(self.repo.workdir)
            self.stickyStatus.emit(self.tr("Initializing submodule {0}: {1}...").format(i, escamp(displayPath)))

            url = ""
            with suppress(RuntimeError):
                url = submodule.url

            # Reset remoteLink state before each submodule
            # (so that we don't tally failed login attempts across submodules)
            self.remoteLink.resetLoginState()

            with self.remoteLink.remoteKeyFileContext(url):
                submodule.update(init=True, callbacks=self.remoteLink)

            subRepo = Repo(path, RepositoryOpenFlag.NO_SEARCH)
            frontier.extend(frontierGenerator(subRepo))

        return; yield None  # bogus yield to make it a generator

    def onError(self, exc: BaseException):
        traceback.print_exception(exc.__class__, exc, exc.__traceback__)
        dialog = self.cloneDialog
        QApplication.beep()
        QApplication.alert(dialog, 500)
        dialog.enableInputs(True)
        dialog.ui.statusForm.setBlurb(f"<span style='white-space: pre;'><b>{TrTables.exceptionName(exc)}:</b> {escape(str(exc))}")
