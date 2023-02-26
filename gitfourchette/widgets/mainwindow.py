from gitfourchette import log
from gitfourchette import porcelain
from gitfourchette import settings
from gitfourchette import tasks
from gitfourchette.globalshortcuts import GlobalShortcuts
from gitfourchette.globalstatus import globalstatus
from gitfourchette.qt import *
from gitfourchette.repostate import RepoState
from gitfourchette.reverseunidiff import reverseUnidiff
from gitfourchette.util import (compactPath, showInFolder, excMessageBox, DisableWidgetContext, QSignalBlockerContext,
                                PersistentFileDialog, setWindowModal, showWarning, showInformation, askConfirmation,
                                paragraphs)
from gitfourchette.widgets.aboutdialog import showAboutDialog
from gitfourchette.widgets.autohidemenubar import AutoHideMenuBar
from gitfourchette.widgets.clonedialog import CloneDialog
from gitfourchette.widgets.customtabwidget import CustomTabWidget
from gitfourchette.widgets.prefsdialog import PrefsDialog
from gitfourchette.widgets.repowidget import RepoWidget
from gitfourchette.widgets.welcomewidget import WelcomeWidget
from html import escape
from typing import Literal
import gc
import os
import pygit2
import re



try:
    import psutil
except ImportError:
    print("psutil isn't available. The memory indicator will not work.")
    psutil = None


class Session:
    openTabs: list[str]
    activeTab: int
    geometry: QRect


class MainWindow(QMainWindow):
    welcomeStack: QStackedWidget
    welcomeWidget: WelcomeWidget
    tabs: CustomTabWidget
    recentMenu: QMenu
    repoMenu: QMenu
    memoryIndicator: QPushButton | None

    def __init__(self):
        super().__init__()

        self.setObjectName("GFMainWindow")

        self.sharedSplitterStates = {}

        self.setWindowTitle(QApplication.applicationDisplayName())
        self.resize(QSize(800, 600))
        self.move(QPoint(50, 50))

        self.tabs = CustomTabWidget(self)
        self.tabs.currentChanged.connect(self.onTabChange)
        self.tabs.tabCloseRequested.connect(self.closeTab)
        self.tabs.tabContextMenuRequested.connect(self.onTabContextMenu)
        self.tabs.tabDoubleClicked.connect(self.onTabDoubleClicked)

        self.welcomeWidget = WelcomeWidget(self)

        self.welcomeStack = QStackedWidget()
        self.welcomeStack.addWidget(self.welcomeWidget)
        self.welcomeStack.addWidget(self.tabs)
        self.welcomeStack.setCurrentWidget(self.welcomeWidget)
        self.setCentralWidget(self.welcomeStack)

        menuBar = self.makeMenu()
        self.setMenuBar(menuBar)
        self.autoHideMenuBar = AutoHideMenuBar(menuBar)

        self.statusProgress = QProgressBar()
        self.statusProgress.setMaximumHeight(16)
        self.statusProgress.setMaximumWidth(128)
        self.statusProgress.setVisible(False)
        self.statusProgress.setTextVisible(False)
        globalstatus.statusText.connect(self.updateStatusMessage)
        globalstatus.progressMaximum.connect(lambda v: self.statusProgress.setMaximum(v))
        globalstatus.progressValue.connect(lambda v: [self.statusProgress.setVisible(True), self.statusProgress.setValue(v)])
        globalstatus.progressDisable.connect(lambda: self.statusProgress.setVisible(False))
        self.statusBar = QStatusBar()
        self.statusBar.setSizeGripEnabled(False)
        self.statusBar.addPermanentWidget(self.statusProgress)
        self.setStatusBar(self.statusBar)
        self.memoryIndicator = None

        self.setAcceptDrops(True)

        QApplication.instance().installEventFilter(self)
        self.refreshPrefs()

    def close(self) -> bool:
        globalstatus.statusText.disconnect()
        globalstatus.progressMaximum.disconnect()
        globalstatus.progressValue.disconnect()
        globalstatus.progressDisable.disconnect()
        return super().close()

    def eventFilter(self, watched, event: QEvent):
        isPress = event.type() == QEvent.Type.MouseButtonPress
        isDblClick = event.type() == QEvent.Type.MouseButtonDblClick

        if (isPress or isDblClick) and self.isActiveWindow():
            mouseEvent: QMouseEvent = event

            isBack = mouseEvent.button() == Qt.MouseButton.BackButton
            isForward = mouseEvent.button() == Qt.MouseButton.ForwardButton

            if isBack or isForward:
                if isPress:
                    rw = self.currentRepoWidget()
                    if rw and isBack:
                        rw.navigateBack()
                    elif rw and isForward:
                        rw.navigateForward()

                # eat navigation clicks or double-clicks
                return True

        return False

    def onMemoryIndicatorClicked(self):
        gc.collect()

        print("Top-Level Windows:")
        for tlw in QApplication.topLevelWindows():
            print("*", tlw)
        print("Top-Level Widgets:")
        for tlw in QApplication.topLevelWidgets():
            print("*", tlw, tlw.objectName())
        print()

        self.updateMemoryIndicator()

    def updateMemoryIndicator(self):
        numQObjects = sum(1 + len(tlw.findChildren(QObject))  # "+1" to account for tlw itself
                          for tlw in QApplication.topLevelWidgets())

        if psutil:
            rss = psutil.Process(os.getpid()).memory_info().rss
            self.memoryIndicator.setText(F"{rss // 1024:,}K {numQObjects:,}Q")
        else:
            self.memoryIndicator.setText(F"{numQObjects:,}Q")

    def updateStatusMessage(self, message):
        self.statusBar.showMessage(message)

    def paintEvent(self, event:QPaintEvent):
        if self.memoryIndicator:
            self.updateMemoryIndicator()
        super().paintEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Alt:
            self.autoHideMenuBar.toggle()

    def makeMenu(self) -> QMenuBar:
        menubar = QMenuBar(self)
        menubar.setObjectName("MWMenuBar")

        # -------------------------------------------------------------

        fileMenu = menubar.addMenu(self.tr("&File"))
        fileMenu.setObjectName("MWFileMenu")

        a = fileMenu.addAction(self.tr("&New Repository..."), self.newRepo)
        a.setShortcuts(QKeySequence.StandardKey.New)

        a = fileMenu.addAction(self.tr("C&lone Repository..."), self.cloneDialog)
        a.setShortcut("Ctrl+Shift+N")

        fileMenu.addSeparator()

        a = fileMenu.addAction(self.tr("&Open Repository..."), self.openDialog)
        a.setShortcuts(QKeySequence.StandardKey.Open)

        self.recentMenu = fileMenu.addMenu(self.tr("Open &Recent"))
        self.recentMenu.setObjectName("RecentMenu")

        a = fileMenu.addAction(self.tr("&Close Tab"), self.closeCurrentTab)
        a.setShortcuts(GlobalShortcuts.closeTab)

        fileMenu.addSeparator()

        a = fileMenu.addAction(self.tr("Apply Patch..."), self.importPatch)
        a.setShortcut("Ctrl+I")

        fileMenu.addAction(self.tr("Reverse Patch..."), lambda: self.importPatch(reverse=True))

        fileMenu.addSeparator()

        a = fileMenu.addAction(self.tr("&Preferences..."), self.openSettings)
        a.setMenuRole(QAction.MenuRole.PreferencesRole)
        a.setShortcuts(QKeySequence.StandardKey.Preferences)

        fileMenu.addSeparator()

        a = fileMenu.addAction(self.tr("&Quit"), self.close)
        a.setMenuRole(QAction.MenuRole.QuitRole)
        a.setShortcuts(QKeySequence.StandardKey.Quit)

        # -------------------------------------------------------------

        repoMenu: QMenu = menubar.addMenu(self.tr("&Repo"))
        repoMenu.setObjectName("MWRepoMenu")
        repoMenu.setEnabled(False)
        self.repoMenu = repoMenu

        a = repoMenu.addAction(self.tr("&Refresh"), self.quickRefresh)
        a.setShortcuts(GlobalShortcuts.refresh)

        a = repoMenu.addAction(self.tr("&Hard Refresh"), self.hardRefresh)
        a.setShortcut("Ctrl+F5")

        repoMenu.addSeparator()

        a = repoMenu.addAction(self.tr("&Commit..."), self.commit)
        a.setShortcuts(GlobalShortcuts.commit)

        a = repoMenu.addAction(self.tr("&Amend Last Commit..."), self.amend)
        a.setShortcuts(GlobalShortcuts.amendCommit)

        a = repoMenu.addAction(self.tr("Stash Changes..."), self.newStash)
        a.setShortcuts(GlobalShortcuts.newStash)

        repoMenu.addSeparator()

        repoMenu.addAction(self.tr("Add Re&mote..."), self.newRemote)

        repoMenu.addSeparator()

        a = repoMenu.addAction(self.tr("&Find Commit..."), lambda: self.currentRepoWidget().findFlow())
        a.setShortcuts(QKeySequence.StandardKey.Find)

        a = repoMenu.addAction(self.tr("Find Next"), lambda: self.currentRepoWidget().findNext())
        a.setShortcuts(QKeySequence.StandardKey.FindNext)

        a = repoMenu.addAction(self.tr("Find Previous"), lambda: self.currentRepoWidget().findPrevious())
        a.setShortcuts(QKeySequence.StandardKey.FindPrevious)

        repoMenu.addSeparator()

        configFilesMenu = repoMenu.addMenu(self.tr("&Local Config Files"))

        a = repoMenu.addAction(self.tr("&Open Repo Folder"), self.openRepoFolder)
        a.setShortcuts(GlobalShortcuts.openRepoFolder)

        repoMenu.addAction(self.tr("Cop&y Repo Path"), self.copyRepoPath)
        repoMenu.addAction(self.tr("Rename Repo..."), self.renameRepo)
        repoMenu.addSeparator()
        repoMenu.addAction(self.tr("Resc&ue Discarded Changes..."), self.openRescueFolder)
        repoMenu.addAction(self.tr("Clear Discarded Changes..."), self.clearRescueFolder)
        repoMenu.addAction(self.tr("Recall Lost Commit..."), self.recallCommit)

        configFilesMenu.addAction(".gitignore", self.openGitignore)
        configFilesMenu.addAction("config", self.openLocalConfig)
        configFilesMenu.addAction("exclude", self.openLocalExclude)

        # -------------------------------------------------------------

        branchMenu = menubar.addMenu(self.tr("&Branch"))
        branchMenu.setObjectName("MWBranchMenu")

        a = branchMenu.addAction(self.tr("New &Branch..."), self.newBranch)
        a.setShortcuts(GlobalShortcuts.newBranch)

        a = branchMenu.addAction(self.tr("&Push Branch..."), self.push)
        a.setShortcuts(GlobalShortcuts.pushBranch)

        a = branchMenu.addAction(self.tr("Pul&l Branch..."), self.pull)
        a.setShortcuts(GlobalShortcuts.pullBranch)

        # -------------------------------------------------------------

        patchMenu = menubar.addMenu(self.tr("&Diff"))
        patchMenu.setObjectName("MWDiffMenu")
        a = patchMenu.addAction(self.tr("&Find in Diff..."), lambda: self.currentRepoWidget().findInDiffFlow())
        a.setShortcut("Ctrl+Alt+F")

        # -------------------------------------------------------------

        goMenu: QMenu = menubar.addMenu(self.tr("&Go"))
        goMenu.setObjectName("MWGoMenu")

        a = goMenu.addAction(self.tr("&Uncommitted Changes"), self.selectUncommittedChanges)
        a.setShortcut("Ctrl+U")

        goMenu.addSeparator()

        a = goMenu.addAction(self.tr("&Next Tab"), self.nextTab)
        a.setShortcut("Ctrl+Tab")

        a = goMenu.addAction(self.tr("&Previous Tab"), self.previousTab)
        a.setShortcut("Ctrl+Shift+Tab")

        goMenu.addSeparator()

        a = goMenu.addAction(self.tr("Next File"), self.nextFile)
        a.setShortcut("Ctrl+]")

        a = goMenu.addAction(self.tr("Previous File"), self.previousFile)
        a.setShortcut("Ctrl+[")

        # -------------------------------------------------------------

        helpMenu = menubar.addMenu(self.tr("&Help"))
        helpMenu.setObjectName("MWHelpMenu")

        a = helpMenu.addAction(self.tr("&About {0}").format(QApplication.applicationDisplayName()), lambda: showAboutDialog(self))
        a.setMenuRole(QAction.AboutRole)

        # -------------------------------------------------------------

        self.fillRecentMenu()

        return menubar

    def onAcceptPrefsDialog(self, dlg: PrefsDialog):
        if not dlg.prefDiff:  # No changes were made to the prefs
            return

        # Apply changes from prefDiff to the actual prefs
        for k in dlg.prefDiff:
            settings.prefs.__dict__[k] = dlg.prefDiff[k]

        # Write prefs to disk
        settings.prefs.write()

        # Apply new style
        if 'qtStyle' in dlg.prefDiff:
            settings.applyQtStylePref(forceApplyDefault=True)
        if 'debug_verbosity' in dlg.prefDiff:
            log.setVerbosity(settings.prefs.debug_verbosity)

        settings.applyLanguagePref()

        # Notify widgets
        self.refreshPrefs()

        info = self.tr("Some changes may require restarting {0} to take effect.").format(QApplication.applicationDisplayName())

        if "language" in dlg.prefDiff:
            info += "\n\n" + self.tr("In particular, some menus and buttons will remain untranslated until you restart the application.")

        showInformation(self, self.tr("Apply Settings"), info)

    def openSettings(self):
        dlg = PrefsDialog(self)
        dlg.accepted.connect(lambda: self.onAcceptPrefsDialog(dlg))
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)  # don't leak dialog
        dlg.show()

    def fillRecentMenu(self):
        def onClearRecents():
            settings.history.clearRepoHistory()
            settings.history.write()
            self.fillRecentMenu()

        self.recentMenu.clear()
        for historic in settings.history.getRecentRepoPaths(settings.prefs.maxRecentRepos):
            self.recentMenu.addAction(compactPath(historic), lambda path=historic: self.openRepo(path))
        self.recentMenu.addSeparator()
        self.recentMenu.addAction(self.tr("Clear"), onClearRecents)

    def currentRepoWidget(self) -> RepoWidget:
        return self.tabs.currentWidget()

    def onTabChange(self, i):
        if i < 0:
            self.setWindowTitle(QApplication.applicationDisplayName())
            return

        # Get out of welcome widget
        self.welcomeStack.setCurrentWidget(self.tabs)

        self.repoMenu.setEnabled(False)
        w = self.currentRepoWidget()
        w.restoreSplitterStates()

        # If we don't have a RepoState, then the tab is lazy-loaded.
        # We need to load it now.
        if not w.isLoaded:
            # Disable tabs widget while we're loading the repo to prevent tabs
            # from accidentally being dragged while the UI is locking up
            with DisableWidgetContext(self.tabs):
                # Load repo
                success = self._loadRepo(w, w.workdir)
                if not success:
                    return
                settings.history.write()

        self.repoMenu.setEnabled(True)
        w.refreshWindowTitle()

    def onTabContextMenu(self, globalPoint: QPoint, i: int):
        if i < 0:  # Right mouse button released outside tabs
            return
        rw: RepoWidget = self.tabs.widget(i)
        menu = QMenu(self)
        menu.setObjectName("MWRepoTabContextMenu")
        closeTabAction = menu.addAction(self.tr("Close Tab"), lambda: self.closeTab(i))
        menu.addAction(self.tr("Close Other Tabs"), lambda: self.closeOtherTabs(i))
        menu.addSeparator()
        openRepoFolderAction = menu.addAction(self.tr("Open Repo Folder"), lambda: self.openRepoFolder(rw))
        menu.addAction(self.tr("Copy Repo Path"), lambda: self.copyRepoPath(rw))
        menu.addAction(self.tr("Rename", "RepoTabCM"), lambda: self.renameRepo(rw))
        menu.addSeparator()
        if rw.state:
            menu.addAction(self.tr("Unload", "RepoTabCM"), lambda: self.unloadTab(i))
        else:
            menu.addAction(self.tr("Load", "RepoTabCM"), lambda: self.loadTab(i))

        if i == self.tabs.currentIndex():
            closeTabAction.setShortcuts(GlobalShortcuts.closeTab)
            openRepoFolderAction.setShortcuts(GlobalShortcuts.openRepoFolder)

        menu.exec(globalPoint)
        menu.deleteLater()

    def onTabDoubleClicked(self, i: int):
        if i < 0:
            return
        rw: RepoWidget = self.tabs.widget(i)
        if settings.prefs.tabs_doubleClickOpensFolder:
            self.openRepoFolder(rw)

    def _constructRepo(self, path: str):
        repo = pygit2.Repository(path)

        if repo.is_shallow:
            raise NotImplementedError(self.tr("Sorry, shallow repositories aren’t supported yet.").format(path))

        if repo.is_bare:
            raise NotImplementedError(self.tr("Sorry, bare repositories aren’t supported yet.").format(path))

        return repo

    def _loadRepo(self, rw: RepoWidget, pathOrRepo: str | pygit2.Repository):
        assert rw

        repo: pygit2.Repository
        path: str

        if type(pathOrRepo) is pygit2.Repository:
            repo = pathOrRepo
            path = repo.workdir
        elif type(pathOrRepo) is str:
            path = pathOrRepo
            repo = self._constructRepo(path)
        else:
            raise TypeError("pathOrRepo must either be an str or a Repository")

        assert repo is not None

        shortname = settings.history.getRepoNickname(path)

        progress = QProgressDialog(self.tr("Opening repository..."), self.tr("Abort"), 0, 0, self)
        progress.setWindowTitle(shortname)
        progress.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.CustomizeWindowHint | Qt.WindowType.WindowTitleHint)  # hide close button
        progress.setMinimumWidth(2 * progress.fontMetrics().horizontalAdvance("000,000,000 commits loaded."))
        progress.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)  # don't leak dialog

        # On macOS, WindowModal triggers a slow animation that makes loading a repo feel gratuitously sluggish.
        # ApplicationModal isn't as bad.
        modality = Qt.WindowModality.ApplicationModal if MACOS else Qt.WindowModality.WindowModal
        setWindowModal(progress, modality)

        if not settings.TEST_MODE:
            progress.show()
        QCoreApplication.processEvents()

        try:
            newState = RepoState(repo)
            commitSequence = newState.loadCommitSequence(progress)

            rw.setRepoState(newState)

            rw.graphView.setHiddenCommits(newState.hiddenCommits)
            rw.graphView.setCommitSequence(commitSequence)
            rw.sidebar.refresh(newState)

            self.refreshTabText(rw)

        except BaseException as exc:
            # In test mode, we really want this to fail
            if settings.TEST_MODE:
                raise exc

            excMessageBox(
                exc,
                message=self.tr("An exception was thrown while opening “{0}”").format(escape(path)),
                parent=self)
            return False

        finally:
            progress.close()

        settings.history.setRepoNumCommits(repo.workdir, len(commitSequence))

        rw.graphView.selectUncommittedChanges()
        return True

    def _openRepo(self, path: str, foreground=True, addToHistory=True) -> RepoWidget | None:
        # Construct a pygit2.Repository so we can get the workdir
        repo = self._constructRepo(path)

        if not repo:
            return None

        workdir = repo.workdir

        # First check that we don't have a tab for this repo already
        for i in range(self.tabs.count()):
            existingRW: RepoWidget = self.tabs.widget(i)
            if os.path.samefile(workdir, existingRW.workdir):
                repo.free()
                del repo
                self.tabs.setCurrentIndex(i)
                return existingRW

        newRW = RepoWidget(self, self.sharedSplitterStates)

        if foreground:
            if not self._loadRepo(newRW, repo):
                newRW.destroy()
                return None  # don't create the tab if opening the repo failed
        else:
            newRW.setPendingWorkdir(workdir)
            repo.free()
            del repo

        tabIndex = self.tabs.addTab(newRW, newRW.getTitle())
        self.tabs.setTabTooltip(tabIndex, compactPath(workdir))

        if foreground:
            self.tabs.setCurrentIndex(tabIndex)

        newRW.nameChange.connect(lambda: self.refreshTabText(newRW))

        if addToHistory:
            settings.history.addRepo(workdir)
            settings.history.write()
            self.fillRecentMenu()

        return newRW

    # -------------------------------------------------------------------------
    # Repo menu callbacks

    @staticmethod
    def needRepoWidget(callback):
        def wrapper(self, rw=None):
            if rw is None:
                rw = self.currentRepoWidget()
            if rw:
                callback(self, rw)
            else:
                QApplication.beep()
        return wrapper

    @needRepoWidget
    def quickRefresh(self, rw: RepoWidget):
        rw.quickRefresh()

    @needRepoWidget
    def hardRefresh(self, rw: RepoWidget):
        self._loadRepo(rw, rw.workdir)

    @needRepoWidget
    def openRepoFolder(self, rw: RepoWidget):
        showInFolder(rw.workdir)

    @needRepoWidget
    def copyRepoPath(self, rw: RepoWidget):
        QApplication.clipboard().setText(rw.workdir)

    @needRepoWidget
    def commit(self, rw: RepoWidget):
        rw.runTask(tasks.NewCommit)

    @needRepoWidget
    def amend(self, rw: RepoWidget):
        rw.runTask(tasks.AmendCommit)

    @needRepoWidget
    def newStash(self, rw: RepoWidget):
        rw.runTask(tasks.NewStash)

    @needRepoWidget
    def newBranch(self, rw: RepoWidget):
        rw.runTask(tasks.NewBranchFromHead)

    @needRepoWidget
    def newRemote(self, rw: RepoWidget):
        rw.runTask(tasks.NewRemote)

    @needRepoWidget
    def renameRepo(self, rw: RepoWidget):
        rw.renameRepo()

    @needRepoWidget
    def push(self, rw: RepoWidget):
        rw.startPushFlow()

    @needRepoWidget
    def pull(self, rw: RepoWidget):
        rw.runTask(tasks.PullBranch)

    @needRepoWidget
    def openRescueFolder(self, rw: RepoWidget):
        rw.openRescueFolder()

    @needRepoWidget
    def clearRescueFolder(self, rw: RepoWidget):
        rw.clearRescueFolder()

    @needRepoWidget
    def recallCommit(self, rw: RepoWidget):
        rw.recallCommit()

    def _openLocalConfigFile(self, fullPath: str):
        def createAndOpen():
            open(fullPath, "ab").close()
            QDesktopServices.openUrl(QUrl.fromLocalFile(fullPath))

        if not os.path.exists(fullPath):
            basename = os.path.basename(fullPath)
            askConfirmation(
                self,
                self.tr("Open “{0}”").format(basename),
                paragraphs(
                    self.tr("There’s no file at this location:") + "<br>" + escape(fullPath),
                    self.tr("Do you want to create it?")),
                okButtonText=self.tr("Create “{0}”").format(basename),
                callback=createAndOpen)
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(fullPath))

    @needRepoWidget
    def openGitignore(self, rw: RepoWidget):
        self._openLocalConfigFile(os.path.join(rw.repo.workdir, ".gitignore"))

    @needRepoWidget
    def openLocalConfig(self, rw: RepoWidget):
        self._openLocalConfigFile(os.path.join(rw.repo.path, "config"))

    @needRepoWidget
    def openLocalExclude(self, rw: RepoWidget):
        self._openLocalConfigFile(os.path.join(rw.repo.path, "info", "exclude"))

    # -------------------------------------------------------------------------
    # File menu callbacks

    def newRepo(self):
        path, _ = PersistentFileDialog.getSaveFileName(self, self.tr("New repository"))
        if not path:
            return
        try:
            pygit2.init_repository(path)
        except BaseException as exc:
            excMessageBox(
                exc,
                self.tr("New repository"),
                self.tr("Couldn’t create an empty repository in “{0}”.").format(escape(path)),
                parent=self,
                icon='warning')
            return
        self.openRepo(path)

    def cloneDialog(self, initialUrl: str = ""):
        dlg = CloneDialog(initialUrl, self)

        dlg.cloneSuccessful.connect(lambda path: self.openRepo(path))

        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        setWindowModal(dlg)
        dlg.show()

    def openDialog(self):
        path = PersistentFileDialog.getExistingDirectory(self, self.tr("Open repository"))
        if path:
            self.openRepo(path)

    def openRepo(self, path):
        try:
            rw = self._openRepo(path)
        except BaseException as exc:
            excMessageBox(
                exc,
                self.tr("Open repository"),
                self.tr("Couldn’t open the repository at “{0}”.").format(escape(path)),
                parent=self,
                icon='warning')
            return None

        self.saveSession()
        return rw

    def importPatch(self, reverse=False):
        if not self.currentRepoWidget() or not self.currentRepoWidget().repo:
            showWarning(self, self.tr("Import patch"), self.tr("Please open a repository before importing a patch."))
            return

        if reverse:
            title = self.tr("Import patch (reverse)")
        else:
            title = self.tr("Import patch")

        patchFileCaption = self.tr("Patch file")
        allFilesCaption = self.tr("All files")

        path, _ = PersistentFileDialog.getOpenFileName(self, title, filter=F"{patchFileCaption} (*.patch);;{allFilesCaption} (*)")
        if not path:
            return

        try:
            with open(path, 'rt', encoding='utf-8') as patchFile:
                patchData = patchFile.read()
            loadedDiff: pygit2.Diff = porcelain.loadPatch(patchData)
        except (IOError,
                UnicodeDecodeError,  # if passing in a random binary file
                KeyError,  # 'no patch found'
                pygit2.GitError) as loadError:
            excMessageBox(loadError, title, self.tr("Can’t load this patch."), parent=self, icon='warning')
            return

        if reverse:
            try:
                patchData = reverseUnidiff(loadedDiff.patch)
                loadedDiff: pygit2.Diff = porcelain.loadPatch(patchData)
            except Exception as reverseError:
                excMessageBox(reverseError, title, self.tr("Can’t reverse this patch."), parent=self, icon='warning')
                return

        repo = self.currentRepoWidget().repo

        try:
            porcelain.patchApplies(repo, patchData)
        except porcelain.MultiFileError as multiFileError:
            message = self.tr("This patch doesn’t apply.")
            for filePath, fileException in multiFileError.fileExceptions.items():
                message += "<br><br><b>" + escape(filePath) + "</b><br>" + escape(str(fileException))
            showWarning(self, title, message)
            return

        try:
            porcelain.applyPatch(repo, loadedDiff, pygit2.GIT_APPLY_LOCATION_WORKDIR)
        except pygit2.GitError as applyError:
            excMessageBox(applyError, title, self.tr("An error occurred while applying this patch."), parent=self, icon='warning')

    # -------------------------------------------------------------------------
    # Tab management

    def closeCurrentTab(self):
        if self.tabs.count() == 0:  # don't attempt to close if no tabs are open
            QApplication.beep()
            return

        self.closeTab(self.tabs.currentIndex())

    def closeTab(self, index: int, singleTab: bool = True):
        widget = self.tabs.widget(index)
        widget.close()  # will call RepoWidget.cleanup
        self.tabs.removeTab(index)
        widget.deleteLater()

        # If that was the last tab, back to welcome widget
        if self.tabs.count() == 0:
            self.welcomeStack.setCurrentWidget(self.welcomeWidget)

        if singleTab:
            self.saveSession()
            gc.collect()

    def closeOtherTabs(self, index: int):
        # First, set this tab as active so an active tab that gets closed doesn't trigger other tabs to load.
        self.tabs.setCurrentIndex(index)

        # Now close all tabs in reverse order but skip the index we want to keep.
        start = self.tabs.count()-1
        for i in range(start, -1, -1):
            if i != index:
                self.closeTab(i, False)

        self.saveSession()
        gc.collect()

    def closeAllTabs(self):
        start = self.tabs.count() - 1
        with QSignalBlockerContext(self.tabs):  # Don't let awaken unloaded tabs
            for i in range(start, -1, -1):  # Close tabs in reverse order
                self.closeTab(i, False)

    def refreshTabText(self, rw):
        index = self.tabs.indexOf(rw)
        self.tabs.tabs.setTabText(index, rw.getTitle())

    def unloadTab(self, index: int):
        rw : RepoWidget = self.tabs.widget(index)
        rw.cleanup()
        gc.collect()
        self.refreshTabText(rw)

    def loadTab(self, index: int):
        rw : RepoWidget = self.tabs.widget(index)
        self._loadRepo(rw, rw.workdir)

    def nextTab(self):
        if self.tabs.count() == 0:
            QApplication.beep()
            return
        index = self.tabs.currentIndex()
        index += 1
        index %= self.tabs.count()
        self.tabs.setCurrentIndex(index)

    def previousTab(self):
        if self.tabs.count() == 0:
            QApplication.beep()
            return
        index = self.tabs.currentIndex()
        index += self.tabs.count() - 1
        index %= self.tabs.count()
        self.tabs.setCurrentIndex(index)

    # -------------------------------------------------------------------------
    # Go menu

    def selectUncommittedChanges(self):
        self.currentRepoWidget().graphView.selectUncommittedChanges()

    def nextFile(self):
        self.currentRepoWidget().selectNextFile(True)

    def previousFile(self):
        self.currentRepoWidget().selectNextFile(False)

    # -------------------------------------------------------------------------
    # Session management

    def restoreSession(self, session: settings.Session):
        self.sharedSplitterStates = {k: settings.decodeBinary(session.splitterStates[k]) for k in session.splitterStates}
        self.restoreGeometry(settings.decodeBinary(session.windowGeometry))

        # Stop here if there are no tabs to load
        if not session.tabs:
            return

        errors = []

        # Normally, changing the current tab will load the corresponding repo in the background.
        # But we don't want to load every repo as we're creating tabs, so temporarily disconnect the signal.
        with QSignalBlockerContext(self.tabs):
            # We might not be able to load all tabs, so we may have to adjust session.activeTabIndex.
            activeTab = -1
            successfulRepos = []

            # Lazy-loading: prepare all tabs, but don't load the repos (foreground=False).
            for i, path in enumerate(session.tabs):
                try:
                    newRepoWidget = self._openRepo(path, foreground=False, addToHistory=False)
                    successfulRepos.append(path)
                except (pygit2.GitError, OSError, NotImplementedError) as exc:
                    # GitError: most errors thrown by pygit2
                    # OSError: e.g. permission denied
                    # NotImplementedError: e.g. shallow/bare repos
                    errors.append((path, exc))
                    continue

                if i == session.activeTabIndex and newRepoWidget is not None:
                    activeTab = self.tabs.count()-1

            # If we failed to load anything, tell the user about it
            if errors:
                self._reportSessionErrors(errors)

            # Update history (don't write it yet - onTabChange will do it below)
            for path in reversed(successfulRepos):
                settings.history.addRepo(path)
            self.fillRecentMenu()

            # Fall back to tab #0 if the previously active tab couldn't be restored
            # (Otherwise welcome page will stick around)
            if activeTab < 0 and len(successfulRepos):
                activeTab = 0

            # Set current tab and load its repo.
            if activeTab >= 0:
                self.tabs.setCurrentIndex(session.activeTabIndex)
                self.onTabChange(session.activeTabIndex)

    def _reportSessionErrors(self, errors: list[tuple[str, BaseException]]):
        numErrors = len(errors)
        text = self.tr("The session couldn’t be restored fully because %n repositories failed to load:", "", numErrors)

        for path, exc in errors:
            errorText = str(exc)

            # Translate some common GitError texts
            if errorText.startswith("Repository not found at "):
                errorText = self.tr("Repository not found at this path.")

            text += F"<small><br><br></small>{escape(path)}<small><br>{errorText}</small>"

        showWarning(self, self.tr("Restore session"), text)

    def saveSession(self):
        session = settings.Session()
        session.windowGeometry = settings.encodeBinary(self.saveGeometry())
        if self.currentRepoWidget():
            session.splitterStates = {s.objectName(): settings.encodeBinary(s.saveState()) for s in self.currentRepoWidget().splittersToSave}
        else:
            session.splitterStates = {}
        session.tabs = [self.tabs.widget(i).workdir for i in range(self.tabs.count())]
        session.activeTabIndex = self.tabs.currentIndex()
        session.write()

    def closeEvent(self, e):
        QApplication.instance().removeEventFilter(self)
        self.saveSession()

        # Close all tabs so RepoWidgets release all their resources.
        # Important so unit tests wind down properly!
        self.closeAllTabs()

        e.accept()

    # -------------------------------------------------------------------------
    # Drag and drop

    @staticmethod
    def getDropOutcomeFromMimeData(mime: QMimeData) -> tuple[Literal["", "open", "clone"], str]:
        if mime.hasUrls() and len(mime.urls()) > 0:
            url: QUrl = mime.urls()[0]
            if url.isLocalFile():
                return "open", url.toLocalFile()
            else:
                return "clone", url.toString()

        elif mime.hasText():
            text = mime.text()
            if os.path.isabs(text) and os.path.exists(text):
                return "open", text
            elif text.startswith(("ssh://", "git+ssh://", "https://", "http://")):
                return "clone", text
            elif re.match(r"^[a-zA-Z0-9-_.]+@.+:.+", text):
                return "clone", text
            else:
                return "", text

        else:
            return "", ""

    def dragEnterEvent(self, event: QDragEnterEvent):
        action, data = self.getDropOutcomeFromMimeData(event.mimeData())
        if action:
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        action, data = self.getDropOutcomeFromMimeData(event.mimeData())
        if action == "clone":
            self.cloneDialog(data)
        elif action == "open":
            self.openRepo(data)

    # -------------------------------------------------------------------------
    # Refresh prefs

    def refreshPrefs(self):
        if settings.prefs.showStatusBar:
            self.statusBar.show()
        else:
            self.statusBar.hide()

        if self.memoryIndicator:
            self.memoryIndicator.deleteLater()
            self.memoryIndicator = None

        if settings.prefs.debug_showMemoryIndicator:
            self.memoryIndicator = QPushButton("Mem")
            self.memoryIndicator.setStyleSheet("border: none;")  # don't let it thicken the status bar
            self.memoryIndicator.setMinimumWidth(128)
            self.memoryIndicator.clicked.connect(lambda e: self.onMemoryIndicatorClicked())
            self.memoryIndicator.setToolTip("Force GC")
            self.memoryIndicator.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self.statusBar.addPermanentWidget(self.memoryIndicator)

        self.tabs.refreshPrefs()
        self.autoHideMenuBar.refreshPrefs()
        for rw in self.tabs.widgets():
            rw.refreshPrefs()
