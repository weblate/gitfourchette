from contextlib import suppress
import logging
import typing
import os
from typing import Literal, Type

from gitfourchette import settings
from gitfourchette import tasks
from gitfourchette.diffview.diffdocument import DiffDocument
from gitfourchette.diffview.diffview import DiffView
from gitfourchette.diffview.specialdiff import SpecialDiffError, ShouldDisplayPatchAsImageDiff
from gitfourchette.diffview.specialdiffview import SpecialDiffView
from gitfourchette.filelists.committedfiles import CommittedFiles
from gitfourchette.filelists.dirtyfiles import DirtyFiles
from gitfourchette.filelists.filelist import FileList
from gitfourchette.filelists.stagedfiles import StagedFiles
from gitfourchette.forms.banner import Banner
from gitfourchette.forms.brandeddialog import showTextInputDialog
from gitfourchette.forms.conflictview import ConflictView
from gitfourchette.forms.openrepoprogress import OpenRepoProgress
from gitfourchette.forms.pushdialog import PushDialog
from gitfourchette.forms.searchbar import SearchBar
from gitfourchette.forms.unloadedrepoplaceholder import UnloadedRepoPlaceholder
from gitfourchette.globalshortcuts import GlobalShortcuts
from gitfourchette.graphview.graphview import GraphView
from gitfourchette.nav import NavHistory, NavLocator, NavContext
from gitfourchette.porcelain import *
from gitfourchette.qt import *
from gitfourchette.repostate import RepoState
from gitfourchette.sidebar.sidebar import Sidebar
from gitfourchette.tasks import RepoTask, TaskEffects, TaskBook, AbortMerge
from gitfourchette.toolbox import *
from gitfourchette.trtables import TrTables
from gitfourchette.unmergedconflict import UnmergedConflict

logger = logging.getLogger(__name__)

FileStackPage = Literal["workdir", "commit"]
DiffStackPage = Literal["text", "special", "conflict"]

FILEHEADER_HEIGHT = 20


class RepoWidget(QStackedWidget):
    nameChange = Signal()
    openRepo = Signal(str, NavLocator)
    openPrefs = Signal(str)
    locatorChanged = Signal(NavLocator)
    historyChanged = Signal()

    busyMessage = Signal(str)
    statusMessage = Signal(str)
    clearStatus = Signal()

    state: RepoState | None

    pendingPath: str
    "Path of the repository if it isn't loaded yet (state=None)"

    pendingLocator: NavLocator
    pendingRefresh: TaskEffects

    allowAutoLoad: bool

    navLocator: NavLocator
    navHistory: NavHistory

    splittersToSave: list[QSplitter]
    sharedSplitterSizes: dict[str, list[int]]

    def __del__(self):
        logger.debug(f"__del__ RepoWidget {self.pendingPath}")

    def __bool__(self):
        """ Override QStackedWidget.__bool__ so we can do quick None comparisons """
        return True

    @property
    def repo(self) -> Repo:
        return self.state.repo if self.state is not None else None

    @property
    def isLoaded(self):
        return self.state is not None

    @property
    def isPriming(self):
        task = self.repoTaskRunner.currentTask
        priming = isinstance(task, tasks.PrimeRepo)
        return priming

    @property
    def workdir(self):
        if self.state:
            return os.path.normpath(self.state.repo.workdir)
        else:
            return self.pendingPath

    def __init__(self, parent: QWidget, pendingWorkdir: str, lazy=False):
        super().__init__(parent)
        self.setObjectName("RepoWidget")

        # Use RepoTaskRunner to schedule git operations to run on a separate thread.
        self.repoTaskRunner = tasks.RepoTaskRunner(self)
        self.repoTaskRunner.postTask.connect(self.refreshPostTask)
        self.repoTaskRunner.progress.connect(self.onRepoTaskProgress)
        self.repoTaskRunner.repoGone.connect(self.onRepoGone)

        self.state = None
        self.pendingPath = os.path.normpath(pendingWorkdir)
        self.pendingLocator = NavLocator()
        self.pendingRefresh = TaskEffects.Nothing
        self.allowAutoLoad = True

        self.busyCursorDelayer = QTimer(self)
        self.busyCursorDelayer.setSingleShot(True)
        self.busyCursorDelayer.setInterval(100)
        self.busyCursorDelayer.timeout.connect(lambda: self.setCursor(Qt.CursorShape.BusyCursor))

        self.navLocator = NavLocator()
        self.navHistory = NavHistory()

        # To be replaced with a shared reference
        self.sharedSplitterSizes = {}

        self.uiReady = False
        self.mainWidgetPlaceholder = None

        if not lazy:
            self.setupUi()
        else:
            # To save some time on boot, we'll call setupUi later if this isn't the foreground RepoWidget.
            # Create placeholder for the main UI until setupUi is called.
            # This is because remove/setPlaceholderWidget expects QStackedLayout slot 0 to be taken by the main UI.
            self.mainWidgetPlaceholder = QWidget(self)
            self.addWidget(self.mainWidgetPlaceholder)

    def setupUi(self):
        if self.uiReady:
            return

        mainLayout = self.layout()
        assert isinstance(mainLayout, QStackedLayout)

        if not mainLayout.isEmpty():
            assert mainLayout.widget(0) is self.mainWidgetPlaceholder
            mainLayout.removeWidget(self.mainWidgetPlaceholder)
            self.mainWidgetPlaceholder.deleteLater()
            self.mainWidgetPlaceholder = None

        # ----------------------------------
        # Splitters

        splitterA = QSplitter(Qt.Orientation.Horizontal, self)
        splitterA.setObjectName("Split_Side")

        splitterB = QSplitter(Qt.Orientation.Vertical, self)
        splitterB.setObjectName("Split_Central")

        splitterC = QSplitter(Qt.Orientation.Horizontal, self)
        splitterC.setObjectName("Split_FL_Diff")

        mainLayout.insertWidget(0, splitterA)

        splitters: list[QSplitter] = self.findChildren(QSplitter)
        assert all(s.objectName() for s in splitters), "all splitters must be named, or state saving won't work!"
        self.splittersToSave = splitters

        # ----------------------------------
        # Build widgets

        sidebarContainer = self._makeSidebarContainer()
        graphContainer = self._makeGraphContainer()
        self.fileStack = self._makeFileStack()
        diffContainer = self._makeDiffContainer()

        diffBanner = Banner(self, orientation=Qt.Orientation.Horizontal)
        diffBanner.setProperty("class", "diff")
        diffBanner.setVisible(False)
        self.diffBanner = diffBanner

        filesDiffContainer = QWidget(self)
        filesDiffLayout = QVBoxLayout(filesDiffContainer)
        filesDiffLayout.setContentsMargins(QMargins())
        filesDiffLayout.setSpacing(2)
        filesDiffLayout.addWidget(splitterC, 1)
        filesDiffLayout.addWidget(diffBanner)

        # ----------------------------------
        # Add widgets in splitters

        splitterA.addWidget(sidebarContainer)
        splitterA.addWidget(splitterB)
        splitterA.setSizes([100, 500])
        splitterA.setStretchFactor(0, 0)  # don't auto-stretch sidebar when resizing window
        splitterA.setStretchFactor(1, 1)

        splitterB.addWidget(graphContainer)
        splitterB.addWidget(filesDiffContainer)
        splitterB.setSizes([100, 150])

        splitterC.addWidget(self.fileStack)
        splitterC.addWidget(diffContainer)
        splitterC.setSizes([100, 300])
        splitterC.setStretchFactor(0, 0)  # don't auto-stretch file lists when resizing window
        splitterC.setStretchFactor(1, 1)

        splitterA.setChildrenCollapsible(False)
        splitterB.setChildrenCollapsible(False)
        splitterC.setChildrenCollapsible(False)

        # ----------------------------------
        # Connect signals

        # save splitter state in splitterMoved signal
        for splitter in self.splittersToSave:
            splitter.splitterMoved.connect(lambda pos, index, s=splitter: self.saveSplitterState(s))

        for fileList in self.dirtyFiles, self.stagedFiles, self.committedFiles:
            # File list view selections are mutually exclusive.
            fileList.nothingClicked.connect(lambda fl=fileList: self.clearDiffView(fl))
            fileList.statusMessage.connect(self.statusMessage)
            fileList.openSubRepo.connect(lambda path: self.openRepo.emit(self.repo.in_workdir(path), NavLocator()))

        self.diffView.contextualHelp.connect(self.statusMessage)

        self.specialDiffView.linkActivated.connect(self.processInternalLink)
        self.graphView.linkActivated.connect(self.processInternalLink)
        self.graphView.statusMessage.connect(self.statusMessage)

        self.committedFiles.openDiffInNewWindow.connect(self.loadPatchInNewWindow)

        self.conflictView.openMergeTool.connect(self.openConflictInMergeTool)
        self.conflictView.openPrefs.connect(self.openPrefs)
        self.conflictView.linkActivated.connect(self.processInternalLink)

        self.sidebar.statusMessage.connect(self.statusMessage)
        self.sidebar.pushBranch.connect(self.startPushFlow)
        self.sidebar.toggleHideRefPattern.connect(self.toggleHideRefPattern)
        self.sidebar.toggleHideStash.connect(self.toggleHideStash)
        self.sidebar.toggleHideAllStashes.connect(self.toggleHideAllStashes)
        self.sidebar.openSubmoduleRepo.connect(self.openSubmoduleRepo)
        self.sidebar.openSubmoduleFolder.connect(self.openSubmoduleFolder)

        # ----------------------------------
        # Connect signals to async tasks
        # (Note: most widgets now use RepoTask.invoke() when they want to launch a task)

        self.amendButton.clicked.connect(lambda: tasks.AmendCommit.invoke(self))
        self.commitButton.clicked.connect(lambda: tasks.NewCommit.invoke(self))
        self.unifiedCommitButton.clicked.connect(lambda: tasks.NewCommit.invoke(self))

        self.restoreSplitterStates()

        # ----------------------------------
        # Prepare placeholder "opening repository" widget

        self.setPlaceholderWidgetOpenRepoProgress()

        # ----------------------------------
        # Styling

        # Huh? Gotta refresh the stylesheet after calling setupUi on a lazy-inited RepoWidget,
        # otherwise fonts somehow appear slightly too large within the RepoWidget on macOS.
        self.setStyleSheet("* {}")

        # Remove sidebar frame
        self.sidebar.setFrameStyle(QFrame.Shape.NoFrame)

        # Smaller font for header text
        for h in (self.diffHeader, self.committedHeader, self.dirtyHeader, self.stagedHeader,
                  self.stageButton, self.unstageButton):
            tweakWidgetFont(h, 90)

        # ----------------------------------
        # We're ready

        self.uiReady = True

    # -------------------------------------------------------------------------
    # Initial layout

    def _makeFileStack(self):
        dirtyContainer = self._makeDirtyContainer()
        stageContainer = self._makeStageContainer()
        committedFilesContainer = self._makeCommittedFilesContainer()

        workdirSplitter = QSplitter(Qt.Orientation.Vertical, self)
        workdirSplitter.addWidget(dirtyContainer)
        workdirSplitter.addWidget(stageContainer)
        workdirSplitter.setObjectName("Split_Workdir")
        workdirSplitter.setChildrenCollapsible(False)

        fileStack = QStackedWidget()
        fileStack.addWidget(workdirSplitter)
        fileStack.addWidget(committedFilesContainer)
        return fileStack

    def _makeDirtyContainer(self):
        header = QElidedLabel(" ")
        header.setObjectName("dirtyHeader")
        header.setToolTip(self.tr("Unstaged files: will not be included in the commit unless you stage them."))
        header.setMinimumHeight(FILEHEADER_HEIGHT)

        dirtyFiles = DirtyFiles(self)

        stageButton = QToolButton()
        stageButton.setObjectName("stageButton")
        stageButton.setText(self.tr("Stage"))
        stageButton.setToolTip(self.tr("Stage selected files"))
        stageButton.setMaximumHeight(FILEHEADER_HEIGHT)
        stageButton.setEnabled(False)
        stageButton.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        appendShortcutToToolTip(stageButton, GlobalShortcuts.stageHotkeys[0])

        stageMenu = ActionDef.makeQMenu(stageButton, [ActionDef(self.tr("Discard..."), dirtyFiles.discard)])
        stageButton.setMenu(stageMenu)
        stageButton.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)

        container = QWidget()
        layout = QGridLayout(container)
        layout.setSpacing(0)  # automatic frameless list views on KDE Plasma 6 Breeze
        layout.setContentsMargins(QMargins())
        layout.addWidget(header,                0, 0)
        layout.addWidget(stageButton,           0, 1)
        layout.addItem(QSpacerItem(1, 1),       1, 0)
        layout.addWidget(dirtyFiles.searchBar,  2, 0, 1, 2)
        layout.addWidget(dirtyFiles,            3, 0, 1, 2)
        layout.setRowStretch(3, 100)

        stageButton.clicked.connect(dirtyFiles.stage)
        dirtyFiles.selectedCountChanged.connect(lambda n: stageButton.setEnabled(n > 0))

        self.dirtyFiles = dirtyFiles
        self.dirtyHeader = header
        self.stageButton = stageButton

        return container

    def _makeStageContainer(self):
        header = QElidedLabel(" ")
        header.setObjectName("stagedHeader")
        header.setToolTip(self.tr("Staged files: will be included in the commit."))
        header.setMinimumHeight(FILEHEADER_HEIGHT)

        stagedFiles = StagedFiles(self)

        unstageButton = QToolButton()
        unstageButton.setObjectName("unstageButton")
        unstageButton.setText(self.tr("Unstage"))
        unstageButton.setToolTip(self.tr("Unstage selected files"))
        unstageButton.setMaximumHeight(FILEHEADER_HEIGHT)
        unstageButton.setEnabled(False)
        unstageButton.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        appendShortcutToToolTip(unstageButton, GlobalShortcuts.discardHotkeys[0])

        commitButtonsContainer = QWidget()
        commitButtonsLayout = QHBoxLayout(commitButtonsContainer)
        commitButtonsLayout.setContentsMargins(0, 0, 0, 0)
        commitButton = QPushButton(self.tr("Commit"))
        amendButton = QPushButton(self.tr("Amend"))
        commitButtonsLayout.addWidget(commitButton)
        commitButtonsLayout.addWidget(amendButton)

        unifiedCommitButton = QToolButton()
        unifiedCommitButton.setText(self.tr("Commit..."))
        unifiedCommitButtonMenu = ActionDef.makeQMenu(unifiedCommitButton, [TaskBook.action(self, tasks.AmendCommit)])
        unifiedCommitButtonMenu = ActionDef.makeQMenu(unifiedCommitButton, [ActionDef(self.tr("Amend Last Commit...Amend Commit...Amend..."), amendButton.click)])

        def unifiedCommitButtonMenuAboutToShow():
            unifiedCommitButtonMenu.setMinimumWidth(unifiedCommitButton.width())
            unifiedCommitButtonMenu.setMaximumWidth(unifiedCommitButton.width())

        def unifiedCommitButtonMenuAboutToHide():
            unifiedCommitButtonMenu.setMinimumWidth(0)

        unifiedCommitButtonMenu.aboutToShow.connect(unifiedCommitButtonMenuAboutToShow)
        unifiedCommitButtonMenu.aboutToHide.connect(unifiedCommitButtonMenuAboutToHide)
        unifiedCommitButton.setMenu(unifiedCommitButtonMenu)
        unifiedCommitButton.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        unifiedCommitButton.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        commitButtonsStack = QStackedWidget()
        commitButtonsStack.addWidget(commitButtonsContainer)
        commitButtonsStack.addWidget(unifiedCommitButton)

        # QToolButtons are unsightly on macOS
        commitButtonsStack.setCurrentIndex(0 if settings.qtIsNativeMacosStyle() else 1)

        # Connect signals
        unstageButton.clicked.connect(stagedFiles.unstage)
        stagedFiles.selectedCountChanged.connect(lambda n: unstageButton.setEnabled(n > 0))

        # Lay out container
        container = QWidget()
        layout = QGridLayout(container)
        layout.setContentsMargins(QMargins())
        layout.setSpacing(0)  # automatic frameless list views on KDE Plasma 6 Breeze
        layout.addWidget(header,                0, 0)
        layout.addWidget(unstageButton,         0, 1)
        layout.addItem(QSpacerItem(1, 1),       1, 0)
        layout.addWidget(stagedFiles.searchBar, 2, 0, 1, 2)  # row col rowspan colspan
        layout.addWidget(stagedFiles,           3, 0, 1, 2)
        layout.addWidget(commitButtonsStack,    4, 0, 1, 2)
        layout.setRowStretch(3, 100)

        # Save references
        self.stagedHeader = header
        self.stagedFiles = stagedFiles
        self.unstageButton = unstageButton
        self.commitButton = commitButton
        self.amendButton = amendButton
        self.unifiedCommitButton = unifiedCommitButton

        return container

    def _makeCommittedFilesContainer(self):
        committedFiles = CommittedFiles(self)

        header = QElidedLabel(" ")
        header.setObjectName("committedHeader")
        header.setMinimumHeight(FILEHEADER_HEIGHT)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(QMargins())
        layout.setSpacing(0)  # automatic frameless list views on KDE Plasma 6 Breeze
        layout.addWidget(header)
        layout.addWidget(committedFiles.searchBar)
        layout.addSpacing(1)
        layout.addWidget(committedFiles)

        self.committedFiles = committedFiles
        self.committedHeader = header
        return container

    def _makeGraphContainer(self):
        graphView = GraphView(self)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(graphView.searchBar)
        layout.addWidget(graphView)

        self.graphView = graphView
        return container

    def _makeDiffContainer(self):
        header = QLabel(" ")
        header.setObjectName("diffHeader")
        header.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        header.setMinimumHeight(FILEHEADER_HEIGHT)
        header.setContentsMargins(0, 0, 4, 0)
        # Don't let header dictate window width if displaying long filename
        header.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Minimum)

        diff = DiffView()

        diffViewContainer = QWidget()
        diffViewContainerLayout = QVBoxLayout(diffViewContainer)
        diffViewContainerLayout.setSpacing(0)
        diffViewContainerLayout.setContentsMargins(0, 0, 0, 0)
        diffViewContainerLayout.addWidget(diff)
        diffViewContainerLayout.addWidget(diff.searchBar)

        specialDiff = SpecialDiffView()

        conflict = ConflictView()
        conflictScroll = QScrollArea()
        conflictScroll.setWidget(conflict)
        conflictScroll.setWidgetResizable(True)

        stack = QStackedWidget()
        # Add widgets in same order as DiffStackPage
        stack.addWidget(diffViewContainer)
        stack.addWidget(specialDiff)
        stack.addWidget(conflictScroll)
        stack.setCurrentIndex(0)

        stackContainer = QWidget()
        layout = QVBoxLayout(stackContainer)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(1)
        layout.addWidget(header)
        layout.addWidget(stack)

        self.diffHeader = header
        self.diffStack = stack
        self.conflictView = conflict
        self.specialDiffView = specialDiff
        self.diffView = diff

        return stackContainer

    def _makeSidebarContainer(self):
        sidebar = Sidebar(self)

        banner = Banner(self, orientation=Qt.Orientation.Vertical)
        banner.setProperty("class", "merge")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(QMargins())
        layout.setSpacing(0)
        layout.addWidget(sidebar)
        layout.addWidget(banner)

        self.sidebar = sidebar
        self.mergeBanner = banner

        return container

    # -------------------------------------------------------------------------
    # Tasks

    def runTask(self, taskClass: Type[RepoTask], *args, **kwargs) -> RepoTask:
        assert issubclass(taskClass, RepoTask)

        # Initialize the task
        task = taskClass(self.repoTaskRunner)
        task.setRepo(self.repo)

        # Enqueue the task
        self.repoTaskRunner.put(task, *args, **kwargs)

        return task

    # -------------------------------------------------------------------------
    # Initial repo priming

    def primeRepo(self, path: str = "", force: bool = False, maxCommits: int = -1):
        if not force and self.isLoaded:
            logger.warning(f"Repo already primed! {path}")
            return None

        primingTask = self.repoTaskRunner.currentTask
        if isinstance(primingTask, tasks.PrimeRepo):
            logger.debug(f"Repo is being primed: {path}")
            return primingTask

        path = path or self.pendingPath
        assert path
        return self.runTask(tasks.PrimeRepo, path=path, maxCommits=maxCommits)

    # -------------------------------------------------------------------------
    # Splitter state

    def setSharedSplitterSizes(self, splitterSizes: dict[str, list[int]]):
        self.sharedSplitterSizes = splitterSizes
        if self.uiReady:
            self.restoreSplitterStates()

    def saveSplitterState(self, splitter: QSplitter):
        # QSplitter.saveState() saves a bunch of properties that we may want to
        # override in later versions, such as whether child widgets are
        # collapsible, the width of the splitter handle, etc. So, don't use
        # saveState(); instead, save the raw sizes for predictable results.
        name = splitter.objectName()
        sizes = splitter.sizes()[:]
        self.sharedSplitterSizes[name] = sizes

    def restoreSplitterStates(self):
        for splitter in self.splittersToSave:
            with suppress(KeyError):
                name = splitter.objectName()
                sizes = self.sharedSplitterSizes[name]
                splitter.setSizes(sizes)

    # -------------------------------------------------------------------------
    # Placeholder widgets

    @property
    def mainStack(self) -> QStackedLayout:
        layout = self.layout()
        assert isinstance(layout, QStackedLayout)
        return layout

    def removePlaceholderWidget(self):
        self.mainStack.setCurrentIndex(0)
        while self.mainStack.count() > 1:
            i = self.mainStack.count() - 1
            w = self.mainStack.widget(i)
            logger.debug(f"Removing modal placeholder widget: {w.objectName()}")
            self.mainStack.removeWidget(w)
            w.deleteLater()
        assert self.mainStack.count() <= 1

    def setPlaceholderWidget(self, w):
        if w is not self.placeholderWidget:
            self.removePlaceholderWidget()
            self.mainStack.addWidget(w)
        self.mainStack.setCurrentWidget(w)
        assert self.mainStack.currentIndex() != 0
        assert self.mainStack.count() <= 2

    def setPlaceholderWidgetOpenRepoProgress(self):
        pw = self.placeholderWidget
        if type(pw) is not OpenRepoProgress:
            name = self.getTitle()
            pw = OpenRepoProgress(self, name)
        self.setPlaceholderWidget(pw)
        return pw

    @property
    def placeholderWidget(self):
        if self.mainStack.count() > 1:
            return self.mainStack.widget(1)
        return None

    # -------------------------------------------------------------------------
    # Navigation

    def saveFilePositions(self):
        if self.navHistory.isWriteLocked():
            logger.warning("Ignoring saveFilePositions because history is locked")
            return

        if self.diffView.isVisibleTo(self):
            newLocator = self.diffView.getPreciseLocator()
            if not newLocator.isSimilarEnoughTo(self.navLocator):
                logger.warning(f"RepoWidget/DiffView locator mismatch: {self.navLocator} vs. {newLocator}")
        else:
            newLocator = self.navLocator.coarse()

        self.navHistory.push(newLocator)
        self.navLocator = newLocator
        return self.navLocator

    def jump(self, locator: NavLocator):
        self.runTask(tasks.Jump, locator)

    def navigateBack(self):
        self.runTask(tasks.JumpBackOrForward, -1)

    def navigateForward(self):
        self.runTask(tasks.JumpBackOrForward, 1)

    # -------------------------------------------------------------------------

    def selectNextFile(self, down=True):
        page = self.fileStackPage()
        if page == "commit":
            widgets = [self.committedFiles]
        elif page == "workdir":
            widgets = [self.dirtyFiles, self.stagedFiles]
        else:
            logger.warning(f"Unknown FileStackPage {page})")
            return

        numWidgets = len(widgets)
        selections = [w.selectedIndexes() for w in widgets]
        lengths = [w.model().rowCount() for w in widgets]

        # find widget to start from: topmost widget that has any selection
        leader = -1
        for i, selection in enumerate(selections):
            if selection:
                leader = i
                break

        if leader < 0:
            # selection empty; pick first non-empty widget as leader
            leader = 0
            row = 0
            while (leader < numWidgets) and (lengths[leader] == 0):
                leader += 1
        else:
            # get selected row in leader widget - TODO: this may not be accurate when multiple rows are selected
            row = selections[leader][-1].row()

            if down:
                row += 1
                while (leader < numWidgets) and (row >= lengths[leader]):
                    # out of rows in leader widget; jump to first row in next widget
                    leader += 1
                    row = 0
            else:
                row -= 1
                while (leader >= 0) and (row < 0):
                    # out of rows in leader widget; jump to last row in prev widget
                    leader -= 1
                    if leader >= 0:
                        row = lengths[leader] - 1

        # if we have a new valid selection, apply it, otherwise bail
        if 0 <= leader < numWidgets and 0 <= row < lengths[leader]:
            widgets[leader].setFocus()
            with QSignalBlockerContext(widgets[leader]):
                widgets[leader].clearSelection()
            widgets[leader].selectRow(row)
        else:
            # No valid selection
            QApplication.beep()

            # Focus on the widget that has some selected files in it
            for w in widgets:
                if len(w.selectedIndexes()) > 0:
                    w.setFocus()
                    break

    def fileListByContext(self, context: NavContext) -> FileList:
        if context == NavContext.STAGED:
            return self.stagedFiles
        elif context == NavContext.UNSTAGED:
            return self.dirtyFiles
        else:
            return self.committedFiles

    # -------------------------------------------------------------------------

    def __repr__(self):
        return f"RepoWidget({self.getTitle()})"

    def getTitle(self) -> str:
        if self.state:
            return self.state.shortName
        elif self.pendingPath:
            return settings.history.getRepoTabName(self.pendingPath)
        else:
            return "???"

    def closeEvent(self, event: QCloseEvent):
        """ Called when closing a repo tab """
        # Don't bother with the placeholder since we'll disappear immediately
        self.cleanup(installPlaceholder=False)

    def cleanup(self, message: str = "", allowAutoReload: bool = True, installPlaceholder: bool = True):
        assert onAppThread()

        # Don't bother with the placeholder widget if we've been lazy-initialized
        installPlaceholder &= self.uiReady
        hasRepo = self.state and self.state.repo

        # Save sidebar collapse cache (if our UI has settled)
        if hasRepo and self.uiReady:
            uiPrefs = self.state.uiPrefs
            if self.sidebar.collapseCacheValid:
                uiPrefs.collapseCache = list(self.sidebar.collapseCache)
            else:
                uiPrefs.collapseCache = []
            try:
                uiPrefs.write()
            except IOError as e:
                logger.warning(f"IOError when writing prefs: {e}")

        # Clear UI
        if installPlaceholder:
            with QSignalBlockerContext(
                    self.committedFiles, self.dirtyFiles, self.stagedFiles,
                    self.graphView, self.sidebar):
                self.committedFiles.clear()
                self.dirtyFiles.clear()
                self.stagedFiles.clear()
                self.graphView.clear()
                self.clearDiffView()
                self.sidebar.model().clear()

        # Let repo wrap up
        if hasRepo:
            # Save path if we want to reload the repo later
            self.pendingPath = os.path.normpath(self.state.repo.workdir)
            self.allowAutoLoad = allowAutoReload

            # Kill any ongoing task then block UI thread until the task dies cleanly
            self.repoTaskRunner.killCurrentTask()
            self.repoTaskRunner.joinZombieTask()

            # Free the repository
            self.state.repo.free()
            self.state.repo = None
            logger.info(f"Repository freed: {self.pendingPath}")

        # Forget RepoState
        self.state = None

        # Install placeholder widget
        if installPlaceholder:
            placeholder = UnloadedRepoPlaceholder(self)
            placeholder.ui.nameLabel.setText(self.getTitle())
            placeholder.ui.loadButton.clicked.connect(lambda: self.primeRepo())
            placeholder.ui.icon.setVisible(False)
            self.setPlaceholderWidget(placeholder)

            if message:
                placeholder.ui.label.setText(message)

            if not allowAutoReload:
                placeholder.ui.icon.setText("")
                placeholder.ui.icon.setPixmap(stockIcon("image-missing").pixmap(96))
                placeholder.ui.icon.setVisible(True)
                placeholder.ui.loadButton.setText(self.tr("Try to reload"))

            # Clean up status bar if there were repo-specific warnings in it
            self.refreshWindowChrome()

    def clearDiffView(self, sourceFileList: FileList | None = None):
        # Ignore clear request if it comes from a widget that doesn't have focus
        if sourceFileList and not sourceFileList.hasFocus():
            return

        self.setDiffStackPage("special")
        self.specialDiffView.clear()
        self.diffView.clear()  # might as well free up any memory taken by DiffView document
        self.diffHeader.setText(" ")

    def renameRepo(self):
        def onAccept(newName):
            settings.history.setRepoNickname(self.workdir, newName)
            settings.history.write()
            self.nameChange.emit()

        currentNickname = settings.history.getRepoNickname(self.workdir)
        dlg = showTextInputDialog(
            self,
            self.tr("Edit repo nickname"),
            self.tr("Enter a new nickname for {0}.<br>This will only be visible within {app} on your machine."
                    ).format(bquoe(currentNickname), app=qAppName()),
            currentNickname,
            onAccept,
            okButtonText=self.tr("Set nickname", "edit repo nickname"))

        buttonBox: QDialogButtonBox = dlg.buttonBox
        resetSB = QDialogButtonBox.StandardButton.RestoreDefaults
        buttonBox.addButton(resetSB)
        buttonBox.button(resetSB).clicked.connect(lambda: onAccept(""))
        buttonBox.button(resetSB).clicked.connect(dlg.close)

    def loadPatchInNewWindow(self, patch: Patch, locator: NavLocator):
        try:
            diffDocument = DiffDocument.fromPatch(patch, locator)
        except Exception as exc:
            excMessageBox(exc, self.tr("Open diff in new window"),
                          self.tr("Only text diffs may be opened in a separate window."),
                          showExcSummary=type(exc) is not ShouldDisplayPatchAsImageDiff,
                          icon='information')
            return

        diffWindow = QWidget(self)
        diffWindow.setObjectName(DiffView.DetachedWindowObjectName)
        diffWindow.setWindowTitle(locator.asTitle())
        diffWindow.setWindowFlag(Qt.WindowType.Window, True)
        diffWindow.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        layout = QVBoxLayout(diffWindow)
        layout.setContentsMargins(QMargins())
        layout.setSpacing(0)
        diff = DiffView(diffWindow)
        diff.isDetachedWindow = True
        diff.setFrameStyle(QFrame.Shape.NoFrame)
        diff.replaceDocument(self.repo, patch, locator, diffDocument)
        layout.addWidget(diff)
        layout.addWidget(diff.searchBar)
        diffWindow.resize(550, 700)
        diffWindow.show()

    def startPushFlow(self, branchName: str = ""):
        pushDialog = PushDialog.startPushFlow(self, self.repo, self.repoTaskRunner, branchName)

    def openSubmoduleRepo(self, submoduleKey: str):
        path = self.repo.get_submodule_workdir(submoduleKey)
        self.openRepo.emit(path, NavLocator())

    def openSubmoduleFolder(self, submoduleKey: str):
        path = self.repo.get_submodule_workdir(submoduleKey)
        openFolder(path)

    # -------------------------------------------------------------------------
    # Conflicts

    def openConflictInMergeTool(self, conflict: DiffConflict):
        self.conflictView.ui.explainer.setText(self.tr("Waiting for merge tool..."))
        umc = UnmergedConflict(self, self.repo, conflict)
        umc.mergeComplete.connect(lambda: self.runTask(tasks.AcceptMergeConflictResolution, umc))
        umc.mergeFailed.connect(lambda code: self.conflictView.onMergeFailed(conflict, code))
        umc.startProcess()

    # -------------------------------------------------------------------------
    # Entry point for generic "Find" command

    def dispatchSearchCommand(self, op: SearchBar.Op):
        focusSinks = [
            [self.dirtyFiles,
             self.dirtyFiles.searchBar.lineEdit, self.stageButton],

            [self.stagedFiles,
             self.stagedFiles.searchBar.lineEdit, self.unstageButton,
             self.commitButton, self.amendButton, self.unifiedCommitButton],

            [self.committedFiles,
             self.committedFiles.searchBar.lineEdit],

            [self.diffView,
             self.diffView.searchBar.lineEdit],

            # Fallback (will be triggered if none of the sinks above have focus)
            [self.graphView],
        ]

        # Find a sink to redirect search to
        focus = self.focusWidget()
        for sinkList in focusSinks:
            # If any of the widgets in sinkList have focus,
            # .search() will be called on the first item in sinkList
            sink = sinkList[0]
            if sink.isVisibleTo(self) and any(focus is widget for widget in sinkList):
                break
        else:
            # Fallback
            sink = focusSinks[-1][0]

        # Forward search
        if isinstance(sink, QAbstractItemView):
            sink.searchBar.searchItemView(op)
        else:
            sink.search(op)

    # -------------------------------------------------------------------------

    def toggleHideRefPattern(self, refPattern: str):
        assert refPattern.startswith("refs/")
        self.state.toggleHideRefPattern(refPattern)
        self.graphView.setHiddenCommits(self.state.hiddenCommits)

    def toggleHideStash(self, stashOid: Oid):
        self.state.toggleHideStash(stashOid)
        self.graphView.setHiddenCommits(self.state.hiddenCommits)

    def toggleHideAllStashes(self):
        self.state.toggleHideAllStashes()
        self.graphView.setHiddenCommits(self.state.hiddenCommits)

    # -------------------------------------------------------------------------

    @property
    def isWorkdirShown(self):
        return self.fileStackPage() == "workdir"

    def setInitialFocus(self):
        """
        Focus on some useful widget within RepoWidget.
        Intended to be called immediately after loading a repo.
        """
        if not self.focusWidget():  # only if nothing has the focus yet
            self.graphView.setFocus()

    def refreshRepo(self, flags: TaskEffects = TaskEffects.DefaultRefresh, jumpTo: NavLocator = NavLocator()):
        """Refresh the repo as soon as possible."""

        if (not self.isLoaded) or self.isPriming:
            return
        assert self.state is not None

        # Break refresh chain?
        if flags == TaskEffects.Nothing:
            if jumpTo:
                logger.warning(f"Refresh chain stopped + dangling jump {jumpTo}")
            return

        if not self.isVisible() or self.repoTaskRunner.isBusy():
            # Can't refresh right now. Stash the effect bits for later.
            logger.debug(f"Stashing refresh bits {repr(flags)}")
            self.pendingRefresh |= flags
            if jumpTo:
                logger.warning(f"Ignoring post-refresh jump {jumpTo} because can't refresh yet")
            return

        # Consume pending effect bits, if any
        if self.pendingRefresh != TaskEffects.Nothing:
            logger.debug(f"Consuming pending refresh bits {self.pendingRefresh}")
            flags |= self.pendingRefresh
            self.pendingRefresh = TaskEffects.Nothing

        # Consume pending locator, if any
        if self.pendingLocator:
            if not jumpTo:
                jumpTo = self.pendingLocator
            else:
                logger.warning(f"Dropping pendingLocator {self.pendingLocator} - overridden by {jumpTo}")
            self.pendingLocator = NavLocator()  # Consume it

        tasks.RefreshRepo.invoke(self, flags, jumpTo)

    def refreshWindowChrome(self):
        shortname = self.getTitle()
        inBrackets = ""
        suffix = ""
        repo = self.repo if self.state else None

        if not repo:
            pass
        elif repo.head_is_unborn:
            inBrackets = self.tr("unborn HEAD")
        elif repo.is_empty:  # getActiveBranchShorthand won't work on an empty repo
            inBrackets = self.tr("repo is empty")
        elif repo.head_is_detached:
            oid = repo.head_commit_oid
            inBrackets = self.tr("detached HEAD @ {0}").format(shortHash(oid))
        else:
            with suppress(GitError):
                inBrackets = repo.head_branch_shorthand

        # Merging? Any conflicts?
        bannerTitle = ""
        bannerText = ""
        bannerHeeded = False
        bannerAction = ""
        bannerCallback = None

        rstate = repo.state() if repo else RepositoryState.NONE

        if not repo:
            pass

        elif rstate == RepositoryState.MERGE:
            bannerTitle = self.tr("Merging")
            try:
                mh = self.state.mergeheadsCache[0]
                name = self.state.reverseRefCache[mh][0]
                name = RefPrefix.split(name)[1]
                bannerTitle = self.tr("Merging {0}").format(bquo(name))
            except (IndexError, KeyError):
                pass

            if not repo.any_conflicts:
                bannerText += self.tr("All conflicts fixed. Commit to conclude.")
                bannerHeeded = True
            else:
                bannerText += self.tr("Conflicts need fixing.")

            bannerAction = self.tr("Abort Merge")
            bannerCallback = lambda: self.runTask(AbortMerge)

        elif rstate == RepositoryState.CHERRYPICK:
            bannerTitle = self.tr("Cherry-picking")

            message = ""
            if not repo.any_conflicts:
                message = self.tr("All conflicts fixed. Commit to conclude.")
                bannerHeeded = True
            else:
                message += self.tr("Conflicts need fixing.")

            bannerText = message
            bannerAction = self.tr("Abort Cherry-Pick")
            bannerCallback = lambda: self.runTask(AbortMerge)

        elif rstate == RepositoryState.NONE:
            if repo.any_conflicts:
                bannerTitle = self.tr("Conflicts")
                bannerText = self.tr("Fix the conflicts among the uncommitted changes.")

        else:
            bannerTitle = self.tr("Warning")
            bannerText = self.tr(
                "The repo is currently in state {state}, which {app} doesn’t support yet. "
                "Use <code>git</code> on the command line to continue."
            ).format(app=qAppName(), state=bquo(rstate.name.replace("_", " ").title()))

        # Set up Banner
        if not self.uiReady:
            pass
        elif bannerText or bannerTitle:
            self.mergeBanner.popUp(bannerTitle, bannerText, heeded=bannerHeeded, canDismiss=False,
                                   buttonLabel=bannerAction, buttonCallback=bannerCallback)
        else:
            self.mergeBanner.setVisible(False)

        if settings.DEVDEBUG:
            chain = []
            if settings.TEST_MODE:
                chain.append("TEST_MODE")
            if settings.SYNC_TASKS:
                chain.append("SYNC_TASKS")
            chain.append(f"PID {os.getpid()}")
            chain.append(QT_BINDING)
            suffix += " - " + ", ".join(chain)

        if inBrackets:
            suffix = F" [{inBrackets}]{suffix}"

        self.window().setWindowTitle(shortname + suffix)

    # -------------------------------------------------------------------------

    def selectRef(self, refName: str):
        oid = self.repo.get_commit_oid_from_refname(refName)
        self.jump(NavLocator(NavContext.COMMITTED, commit=oid))

    # -------------------------------------------------------------------------

    def refreshPostTask(self, task: tasks.RepoTask):
        if task.didSucceed:
            self.refreshRepo(task.effects(), task.jumpTo)
        else:
            self.refreshRepo()

    def onRepoTaskProgress(self, progressText: str, withSpinner: bool = False):
        if withSpinner:
            self.busyMessage.emit(progressText)
        elif progressText:
            self.statusMessage.emit(progressText)
        else:
            self.clearStatus.emit()

        if not withSpinner:
            self.busyCursorDelayer.stop()
            self.setCursor(Qt.CursorShape.ArrowCursor)
        elif not self.busyCursorDelayer.isActive():
            self.busyCursorDelayer.start()

    def onRepoGone(self):
        message = self.tr("Repository folder went missing:") + "\n" + escamp(self.pendingPath)

        # Unload the repo
        self.cleanup(message=message, allowAutoReload=False)

        # Surround repo name with parentheses in tab widget and title bar
        self.nameChange.emit()

    def refreshPrefs(self):
        if not self.uiReady:
            return

        self.diffView.refreshPrefs()
        self.graphView.refreshPrefs()
        self.conflictView.refreshPrefs()
        self.sidebar.refreshPrefs()
        self.dirtyFiles.refreshPrefs()
        self.stagedFiles.refreshPrefs()
        self.committedFiles.refreshPrefs()

        # Reflect any change in titlebar prefs
        if self.isVisible():
            self.refreshWindowChrome()

    # -------------------------------------------------------------------------

    def processInternalLink(self, url: QUrl | str):
        if not isinstance(url, QUrl):
            url = QUrl(url)

        if url.isLocalFile():
            locator = NavLocator()
            fragment = url.fragment()
            if fragment:
                with suppress(ValueError):
                    locator = NavLocator.inCommit(Oid(hex=fragment))

            self.openRepo.emit(url.toLocalFile(), locator)
            return

        if url.scheme() != APP_URL_SCHEME:
            logger.warning(f"Unsupported scheme in internal link: {url.toDisplayString()}")
            return

        logger.info(f"Internal link: {url.toDisplayString()}")

        simplePath = url.path().removeprefix("/")
        kwargs = {k: v for k, v in QUrlQuery(url).queryItems(QUrl.ComponentFormattingOption.FullyDecoded)}

        if url.authority() == NavLocator.URL_AUTHORITY:
            locator = NavLocator.parseUrl(url)
            self.jump(locator)
        elif url.authority() == "refresh":
            self.refreshRepo()
        elif url.authority() == "expandlog":
            try:
                n = int(kwargs["n"])
            except KeyError:
                n = self.state.nextTruncationThreshold
            # After loading, jump back to what is currently the last commit
            self.pendingLocator = NavLocator.inCommit(self.state.commitSequence[-1].oid)
            # Reload the repo
            self.primeRepo(force=True, maxCommits=n)
        elif url.authority() == "opensubfolder":
            p = os.path.join(self.repo.workdir, simplePath)
            self.openRepo.emit(p, NavLocator())
        elif url.authority() == "prefs":
            self.openPrefs.emit(simplePath)
        elif url.authority() == "exec":
            cmdName = simplePath
            taskClass = tasks.__dict__[cmdName]
            self.runTask(taskClass, **kwargs)
        else:
            logger.warning(f"Unsupported authority in internal link: {url.toDisplayString()}")

    # -------------------------------------------------------------------------

    @property
    def _fileStackPageValues(self):
        return typing.get_args(FileStackPage)

    def fileStackPage(self) -> FileStackPage:
        return self._fileStackPageValues[self.fileStack.currentIndex()]

    def setFileStackPage(self, p: FileStackPage):
        self.fileStack.setCurrentIndex(self._fileStackPageValues.index(p))

    def setFileStackPageByContext(self, context: NavContext):
        page: FileStackPage = "workdir" if context.isWorkdir() else "commit"
        self.setFileStackPage(page)

    @property
    def _diffStackPageValues(self):
        return typing.get_args(DiffStackPage)

    def diffStackPage(self) -> DiffStackPage:
        return self._diffStackPageValues[self.diffStack.currentIndex()]

    def setDiffStackPage(self, p: DiffStackPage):
        self.diffStack.setCurrentIndex(self._diffStackPageValues.index(p))
