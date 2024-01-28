from contextlib import suppress
import logging
import typing
import os
from typing import Literal, Type

from gitfourchette import settings
from gitfourchette import tasks
from gitfourchette.diffview.diffdocument import DiffDocument
from gitfourchette.diffview.diffview import DiffView
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
from gitfourchette.sidebar.sidebarmodel import SidebarTabMode, MODAL_SIDEBAR
from gitfourchette.sidebar.sidebarmodetabs import SidebarModeTabs
from gitfourchette.tasks import RepoTask, TaskEffects, TaskBook, AbortMerge
from gitfourchette.toolbox import *
from gitfourchette.trtables import TrTables
from gitfourchette.unmergedconflict import UnmergedConflict

logger = logging.getLogger(__name__)

FileStackPage = Literal["workdir", "commit"]
DiffStackPage = Literal["text", "special", "conflict"]


class RepoWidget(QWidget):
    nameChange = Signal()
    openRepo = Signal(str)
    openPrefs = Signal(str)

    busyMessage = Signal(str)
    statusMessage = Signal(str)
    clearStatus = Signal()

    state: RepoState | None

    pathPending: str
    "Path of the repository if it isn't loaded yet (state=None)"

    allowAutoLoad: bool

    navLocator: NavLocator
    navHistory: NavHistory

    splittersToSave: list[QSplitter]
    sharedSplitterSizes: dict[str, list[int]]

    def __del__(self):
        logger.debug(f"__del__ RepoWidget {self.pathPending}")

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
            return self.pathPending

    def __init__(self, parent: QWidget):
        super().__init__(parent)

        self.setObjectName("RepoWidget")

        # Use RepoTaskRunner to schedule git operations to run on a separate thread.
        self.repoTaskRunner = tasks.RepoTaskRunner(self)
        self.repoTaskRunner.refreshPostTask.connect(self.refreshPostTask)
        self.repoTaskRunner.progress.connect(self.onRepoTaskProgress)
        self.repoTaskRunner.repoGone.connect(self.onRepoGone)

        self.state = None
        self.pathPending = ""
        self.allowAutoLoad = True

        self.busyCursorDelayer = QTimer(self)
        self.busyCursorDelayer.setSingleShot(True)
        self.busyCursorDelayer.setInterval(100)
        self.busyCursorDelayer.timeout.connect(lambda: self.setCursor(Qt.CursorShape.BusyCursor))

        self.navLocator = NavLocator()
        self.navHistory = NavHistory()

        # ----------------------------------
        # Build widgets

        sidebarContainer = self._makeSidebarContainer()
        graphContainer = self._makeGraphContainer()
        self.filesStack = self._makeFilesStack()
        diffContainer = self._makeDiffContainer()

        diffBanner = Banner(self, orientation=Qt.Orientation.Horizontal)
        diffBanner.setProperty("class", "diff")
        diffBanner.setVisible(False)
        self.diffBanner = diffBanner

        # ----------------------------------
        # Splitters

        bottomSplitter = QSplitter(Qt.Orientation.Horizontal)
        bottomSplitter.setObjectName("BottomSplitter")
        bottomSplitter.addWidget(self.filesStack)
        bottomSplitter.addWidget(diffContainer)
        bottomSplitter.setSizes([100, 300])
        bottomSplitter.setStretchFactor(0, 0)  # don't auto-stretch file lists when resizing window
        bottomSplitter.setStretchFactor(1, 1)
        bottomSplitter.setChildrenCollapsible(False)

        bottomContainerLayout = QVBoxLayout()
        bottomContainerLayout.setContentsMargins(0,0,0,0)
        bottomContainerLayout.setSpacing(2)
        bottomContainerLayout.addWidget(bottomSplitter, 1)
        bottomContainerLayout.addWidget(diffBanner)
        bottomContainer = QWidget()
        bottomContainer.setLayout(bottomContainerLayout)

        mainSplitter = QSplitter(Qt.Orientation.Vertical)
        mainSplitter.setObjectName("CentralSplitter")
        mainSplitter.addWidget(graphContainer)
        mainSplitter.addWidget(bottomContainer)
        mainSplitter.setSizes([100, 150])
        mainSplitter.setChildrenCollapsible(False)

        sideSplitter = QSplitter(Qt.Orientation.Horizontal)
        sideSplitter.setChildrenCollapsible(False)
        sideSplitter.setObjectName("SideSplitter")
        sideSplitter.addWidget(sidebarContainer)
        sideSplitter.addWidget(mainSplitter)
        sideSplitter.setSizes([100, 500])
        sideSplitter.setStretchFactor(0, 0)  # don't auto-stretch sidebar when resizing window
        sideSplitter.setStretchFactor(1, 1)
        sideSplitter.setChildrenCollapsible(False)

        mainLayout = QStackedLayout()
        mainLayout.addWidget(sideSplitter)
        self.setLayout(mainLayout)

        self.sharedSplitterSizes = {}

        splitters: list[QSplitter] = self.findChildren(QSplitter)
        assert all(s.objectName() for s in splitters), "all splitters must be named, or state saving won't work!"
        self.splittersToSave = splitters

        # ----------------------------------
        # Styling

        self.sidebar.setFrameStyle(QFrame.Shape.NoFrame)

        # ----------------------------------
        # Connect signals

        # save splitter state in splitterMoved signal
        for splitter in self.splittersToSave:
            splitter.splitterMoved.connect(lambda pos, index, splitter=splitter: self.saveSplitterState(splitter))

        for fileList in [self.dirtyFiles, self.stagedFiles, self.committedFiles]:
            # File list view selections are mutually exclusive.
            for otherFileList in [self.dirtyFiles, self.stagedFiles, self.committedFiles]:
                if fileList != otherFileList:
                    fileList.jump.connect(otherFileList.clearSelection)
            fileList.nothingClicked.connect(lambda fl=fileList: self.clearDiffView(fl))
            fileList.statusMessage.connect(self.statusMessage)

        self.diffView.contextualHelp.connect(self.statusMessage)

        self.specialDiffView.anchorClicked.connect(self.processInternalLink)
        self.graphView.linkActivated.connect(self.processInternalLink)
        self.graphView.statusMessage.connect(self.statusMessage)

        self.committedFiles.openDiffInNewWindow.connect(self.loadPatchInNewWindow)

        self.conflictView.openMergeTool.connect(self.openConflictInMergeTool)
        self.conflictView.openPrefs.connect(self.openPrefs)
        self.conflictView.linkActivated.connect(self.processInternalLink)

        self.sidebar.statusMessage.connect(self.statusMessage)
        self.sidebar.pushBranch.connect(self.startPushFlow)
        self.sidebar.toggleHideBranch.connect(self.toggleHideBranch)
        self.sidebar.toggleHideStash.connect(self.toggleHideStash)
        self.sidebar.toggleHideAllStashes.connect(self.toggleHideAllStashes)
        self.sidebar.toggleHideRemote.connect(self.toggleHideRemote)
        self.sidebar.openSubmoduleRepo.connect(self.openSubmoduleRepo)
        self.sidebar.openSubmoduleFolder.connect(self.openSubmoduleFolder)

        # ----------------------------------
        # Connect signals to async tasks

        self.connectTask(self.amendButton.clicked,              tasks.AmendCommit, argc=0)
        self.connectTask(self.commitButton.clicked,             tasks.NewCommit, argc=0)
        self.connectTask(self.committedFiles.jump,              tasks.Jump)
        self.connectTask(self.diffView.applyPatch,              tasks.ApplyPatch)
        self.connectTask(self.diffView.revertPatch,             tasks.RevertPatch)
        self.connectTask(self.dirtyFiles.discardFiles,          tasks.DiscardFiles)
        self.connectTask(self.dirtyFiles.discardModeChanges,    tasks.DiscardModeChanges)
        self.connectTask(self.dirtyFiles.jump,                  tasks.Jump)
        self.connectTask(self.dirtyFiles.stageFiles,            tasks.StageFiles)
        self.connectTask(self.dirtyFiles.stashFiles,            tasks.NewStash)
        self.connectTask(self.graphView.jump,                   tasks.Jump)
        self.connectTask(self.sidebar.jump,                     tasks.Jump)
        self.connectTask(self.stagedFiles.jump,                 tasks.Jump)
        self.connectTask(self.stagedFiles.stashFiles,           tasks.NewStash)
        self.connectTask(self.stagedFiles.unstageFiles,         tasks.UnstageFiles)
        self.connectTask(self.stagedFiles.unstageModeChanges,   tasks.UnstageModeChanges)
        self.connectTask(self.unifiedCommitButton.clicked,      tasks.NewCommit, argc=0)

    # -------------------------------------------------------------------------
    # Initial layout

    def _makeFilesStack(self):
        dirtyContainer = self._makeDirtyContainer()
        stageContainer = self._makeStageContainer()
        committedFilesContainer = self._makeCommittedFilesContainer()

        workdirSplitter = QSplitter(Qt.Orientation.Vertical)
        workdirSplitter.addWidget(dirtyContainer)
        workdirSplitter.addWidget(stageContainer)
        workdirSplitter.setObjectName("WorkdirSplitter")
        workdirSplitter.setChildrenCollapsible(False)

        filesStack = QStackedWidget()
        filesStack.addWidget(workdirSplitter)
        filesStack.addWidget(committedFilesContainer)

        return filesStack

    def _makeDirtyContainer(self):
        header = QElidedLabel(" ")
        header.setToolTip(self.tr("Unstaged files: will not be included in the commit unless you stage them."))

        dirtyFiles = DirtyFiles(self)

        stageButton = QToolButton()
        stageButton.setText(self.tr("Stage"))
        stageButton.setToolTip(self.tr("Stage selected files"))
        stageButton.setMaximumHeight(24)
        stageButton.setEnabled(False)
        appendShortcutToToolTip(stageButton, GlobalShortcuts.stageHotkeys[0])

        stageMenu = ActionDef.makeQMenu(stageButton, [ActionDef(self.tr("Discard..."), dirtyFiles.discard)])
        stageButton.setMenu(stageMenu)
        stageButton.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)

        layout = QGridLayout()
        layout.setSpacing(1)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(header, 0, 0)
        layout.addWidget(stageButton, 0, 1)
        layout.addWidget(dirtyFiles.searchBar,  1, 0, 1, 2)
        layout.addWidget(dirtyFiles,            2, 0, 1, 2)
        layout.setRowStretch(2, 100)

        header.setBuddy(dirtyFiles)

        stageButton.clicked.connect(dirtyFiles.stage)
        dirtyFiles.selectedCountChanged.connect(lambda n: stageButton.setEnabled(n > 0))

        container = QWidget()
        container.setLayout(layout)

        self.dirtyFiles = dirtyFiles
        self.dirtyHeader = header
        self.stageButton = stageButton

        return container

    def _makeStageContainer(self):
        header = QElidedLabel(" ")
        header.setToolTip(self.tr("Staged files: will be included in the commit."))

        stagedFiles = StagedFiles(self)

        unstageButton = QToolButton()
        unstageButton.setText(self.tr("Unstage"))
        unstageButton.setToolTip(self.tr("Unstage selected files"))
        unstageButton.setMaximumHeight(24)
        unstageButton.setEnabled(False)
        appendShortcutToToolTip(unstageButton, GlobalShortcuts.discardHotkeys[0])

        commitButtonsLayout = QHBoxLayout()
        commitButtonsLayout.setContentsMargins(0, 0, 0, 0)
        commitButton = QPushButton(self.tr("Commit"))
        amendButton = QPushButton(self.tr("Amend"))
        commitButtonsLayout.addWidget(commitButton)
        commitButtonsLayout.addWidget(amendButton)
        commitButtonsContainer = QWidget()
        commitButtonsContainer.setLayout(commitButtonsLayout)

        unifiedCommitButton = QToolButton()
        unifiedCommitButton.setText(self.tr("Commit..."))
        unifiedCommitButtonMenu = ActionDef.makeQMenu(unifiedCommitButton, [TaskBook.action(tasks.AmendCommit)])
        unifiedCommitButtonMenu = ActionDef.makeQMenu(unifiedCommitButton, [ActionDef(self.tr("Amend..."), amendButton.click)])

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

        # Connect signals and buddies
        header.setBuddy(stagedFiles)
        unstageButton.clicked.connect(stagedFiles.unstage)
        stagedFiles.selectedCountChanged.connect(lambda n: unstageButton.setEnabled(n > 0))

        # Lay out container
        layout = QGridLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(header, 0, 0)
        layout.addWidget(unstageButton, 0, 1)
        layout.addWidget(stagedFiles.searchBar, 1, 0, 1, 2)  # row col rowspan colspan
        layout.addWidget(stagedFiles,           2, 0, 1, 2)
        layout.addWidget(commitButtonsStack,    3, 0, 1, 2)
        layout.setRowStretch(2, 100)
        container = QWidget()
        container.setLayout(layout)

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

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)
        layout.addWidget(header)
        layout.addWidget(committedFiles.searchBar)
        layout.addWidget(committedFiles)

        container = QWidget()
        container.setLayout(layout)

        self.committedFiles = committedFiles
        self.committedHeader = header
        return container

    def _makeGraphContainer(self):
        graphView = GraphView(self)

        layout = QVBoxLayout()
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(graphView.searchBar)
        layout.addWidget(graphView)

        container = QWidget()
        container.setLayout(layout)

        self.graphView = graphView
        return container

    def _makeDiffContainer(self):
        header = QElidedLabel(" ")
        header.setElideMode(Qt.TextElideMode.ElideMiddle)
        header.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        header.setMinimumHeight(24)

        diff = DiffView()

        diffViewContainerLayout = QVBoxLayout()
        diffViewContainerLayout.setSpacing(0)
        diffViewContainerLayout.setContentsMargins(0, 0, 0, 0)
        diffViewContainerLayout.addWidget(diff)
        diffViewContainerLayout.addWidget(diff.searchBar)
        diffViewContainer = QWidget()
        diffViewContainer.setLayout(diffViewContainerLayout)

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

        layout = QVBoxLayout()
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(1)
        layout.addWidget(header)
        layout.addWidget(stack)

        stackContainer = QWidget()
        stackContainer.setLayout(layout)

        self.diffHeader = header
        self.diffStack = stack
        self.conflictView = conflict
        self.specialDiffView = specialDiff
        self.diffView = diff

        return stackContainer

    def _makeSidebarContainer(self):
        sidebar = Sidebar(self)

        modeTabs = None
        if MODAL_SIDEBAR:
            repoName = QElidedLabel("RepoName")
            self.nameChange.connect(lambda: repoName.setText(self.getTitle()))
            tweakWidgetFont(repoName, 110)
            repoName.setContentsMargins(4, 8, 0, 0)

            modeTabs = SidebarModeTabs(self)
            modeTabs.setUsesScrollButtons(False)
            modeTabs.currentChanged.connect(lambda i: sidebar.switchMode(modeTabs.tabData(i)))
            modeTabs.setSizePolicy(QSizePolicy.Policy.Minimum, modeTabs.sizePolicy().verticalPolicy())

            tweakWidgetFont(modeTabs, 80)
            with QSignalBlockerContext(modeTabs):
                iconTable = {
                    SidebarTabMode.Tags: "git-tag",
                    SidebarTabMode.Submodules: "git-submodule",
                    SidebarTabMode.Stashes: "git-stash",
                    SidebarTabMode.Branches: "git-branch",
                }
                for mode in SidebarTabMode:
                    if mode == SidebarTabMode.NonModal:
                        continue
                    i = modeTabs.count()
                    name = TrTables.sidebarMode(mode)
                    tip = appendShortcutToToolTipText(name, QKeySequence(f"Ctrl+{i+1}"))
                    modeTabs.addTab(name[:2])
                    modeTabs.setTabData(i, mode)
                    modeTabs.setTabToolTip(i, tip)
                    modeTabs.setTabIcon(i, stockIcon(iconTable[mode]))

            modeTabs.currentChanged.emit(modeTabs.currentIndex())

        banner = Banner(self, orientation=Qt.Orientation.Vertical)
        banner.setProperty("class", "merge")

        layout = QVBoxLayout()
        layout.setContentsMargins(0,0,0,0)
        if MODAL_SIDEBAR:
            layout.setSpacing(0)
            layout.addWidget(repoName)
            layout.addSpacing(8)
            layout.addWidget(modeTabs)
        layout.addWidget(sidebar)
        layout.addWidget(banner)

        container = QWidget()
        container.setLayout(layout)

        self.sidebar = sidebar
        self.sidebarTabs = modeTabs
        self.mergeBanner = banner

        return container

    # -------------------------------------------------------------------------
    # Tasks

    def initTask(self, taskClass: Type[RepoTask]):
        assert issubclass(taskClass, RepoTask)
        task = taskClass(self.repoTaskRunner)
        task.setRepo(self.repo)
        return task

    def runTask(self, taskClass: Type[RepoTask], *args, **kwargs) -> RepoTask:
        task = self.initTask(taskClass)
        self.repoTaskRunner.put(task, *args, **kwargs)
        return task

    def connectTask(self, signal: Signal, taskClass: Type[RepoTask], argc: int = -1):
        def createTask(*args):
            if argc >= 0:
                args = args[:argc]
            return self.runTask(taskClass, *args)
        signal.connect(createTask)

    # -------------------------------------------------------------------------
    # Initial repo priming

    def primeRepo(self, path: str = "", force: bool = False):
        if not force and self.isLoaded:
            logger.warning(f"Repo already primed! {path}")
            return None

        primingTask = self.repoTaskRunner.currentTask
        if isinstance(primingTask, tasks.PrimeRepo):
            logger.debug(f"Repo is being primed: {path}")
            return primingTask

        path = path or self.pathPending
        assert path
        return self.runTask(tasks.PrimeRepo, path)

    # -------------------------------------------------------------------------
    # Splitter state

    def setSharedSplitterSizes(self, splitterSizes: dict[str, list[int]]):
        self.sharedSplitterSizes = splitterSizes
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
        self.removePlaceholderWidget()
        self.mainStack.addWidget(w)
        self.mainStack.setCurrentWidget(w)
        assert self.mainStack.currentIndex() != 0
        assert self.mainStack.count() <= 2

    @property
    def placeholderWidget(self):
        if self.mainStack.count() > 1:
            return self.mainStack.widget(1)
        return None

    # -------------------------------------------------------------------------
    # Navigation

    def saveFilePositions(self):
        if self.diffStack.currentWidget() is self.diffView:
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

    # -------------------------------------------------------------------------

    def __repr__(self):
        return f"RepoWidget({self.getTitle()})"

    def getTitle(self) -> str:
        if self.state:
            return self.state.shortName
        elif self.pathPending:
            return settings.history.getRepoTabName(self.pathPending)
        else:
            return "???"

    def closeEvent(self, event: QCloseEvent):
        """ Called when closing a repo tab """
        self.cleanup()

    def cleanup(self, message: str = "", allowAutoReload: bool = True):
        assert onAppThread()

        hasRepo = self.state and self.state.repo

        # Save sidebar collapse cache
        if hasRepo:
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
        with QSignalBlockerContext(
                self.committedFiles, self.dirtyFiles, self.stagedFiles,
                self.graphView, self.sidebar):
            self.committedFiles.clear()
            self.dirtyFiles.clear()
            self.stagedFiles.clear()
            self.graphView.clear()
            self.clearDiffView()
            self.sidebar.model().clear()

        if hasRepo:
            # Save path if we want to reload the repo later
            self.pathPending = os.path.normpath(self.state.repo.workdir)
            self.allowAutoLoad = allowAutoReload

            # Kill any ongoing task then block UI thread until the task dies cleanly
            self.repoTaskRunner.killCurrentTask()
            self.repoTaskRunner.joinZombieTask()

            # Free the repository
            self.state.repo.free()
            self.state.repo = None
            logger.info(f"Repository freed: {self.pathPending}")

        self.state = None

        # Install placeholder widget
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

        self.setDiffStackPage("text")
        self.diffView.clear()
        self.diffHeader.setText(" ")

    def setPendingWorkdir(self, path):
        self.pathPending = os.path.normpath(path)

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

    def setNoCommitSelected(self):
        self.saveFilePositions()
        self.navLocator = NavLocator()

        self.setFileStackPage("workdir")
        self.committedFiles.clear()

        self.clearDiffView()

    def loadPatchInNewWindow(self, patch: Patch, locator: NavLocator):
        with NonCriticalOperation(self.tr("Load diff in new window")):
            diffWindow = DiffView(self)
            diffWindow.replaceDocument(self.repo, patch, locator, DiffDocument.fromPatch(patch, locator))
            diffWindow.resize(550, 700)
            diffWindow.setWindowTitle(locator.asTitle())
            diffWindow.setWindowFlag(Qt.WindowType.Window, True)
            diffWindow.setFrameStyle(QFrame.Shape.NoFrame)
            diffWindow.show()
            diffWindow.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

    def startPushFlow(self, branchName: str = ""):
        pushDialog = PushDialog.startPushFlow(self, self.repo, self.repoTaskRunner, branchName)

    def openSubmoduleRepo(self, submoduleKey: str):
        path = self.repo.get_submodule_workdir(submoduleKey)
        self.openRepo.emit(path)

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

    def toggleHideBranch(self, branchName: str):
        assert branchName.startswith("refs/")
        self.state.toggleHideBranch(branchName)
        self.graphView.setHiddenCommits(self.state.hiddenCommits)

    def toggleHideStash(self, stashOid: Oid):
        self.state.toggleHideStash(stashOid)
        self.graphView.setHiddenCommits(self.state.hiddenCommits)

    def toggleHideAllStashes(self):
        self.state.toggleHideAllStashes()
        self.graphView.setHiddenCommits(self.state.hiddenCommits)
        self.sidebar.refresh(self.state)

    def toggleHideRemote(self, remoteName: str):
        self.state.toggleHideRemote(remoteName)
        self.graphView.setHiddenCommits(self.state.hiddenCommits)
        self.sidebar.refresh(self.state)

    # -------------------------------------------------------------------------

    @property
    def isWorkdirShown(self):
        return self.fileStackPage() == "workdir"

    def refreshRepo(self, flags: TaskEffects = TaskEffects.DefaultRefresh, jumpTo: NavLocator = None):
        if not self.state:
            return

        if flags == TaskEffects.Nothing:
            return

        if flags & TaskEffects.Workdir:
            self.state.workdirStale = True

        self.runTask(tasks.RefreshRepo, flags, jumpTo)

    def setInitialFocus(self):
        """
        Focus on some useful widget within RepoWidget.
        Intended to be called immediately after loading a repo.
        """
        if not self.focusWidget():  # only if nothing has the focus yet
            self.graphView.setFocus()

    def onRegainForeground(self):
        """Refresh the repo as soon as possible."""

        if (not self.isLoaded) or self.isPriming:
            return

        if self.isVisible() and not self.repoTaskRunner.isBusy():
            self.refreshRepo(TaskEffects.DefaultRefresh | TaskEffects.Workdir)
        else:
            self.state.workdirStale = True

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

        elif rstate in [RepositoryState.REBASE, RepositoryState.REBASE_MERGE]:
            bannerTitle = self.tr("Rebasing")

        elif rstate == RepositoryState.REBASE_INTERACTIVE:
            bannerTitle = self.tr("Rebasing interactively")

        elif repo.any_conflicts:
            bannerTitle = self.tr("Conflicts")
            bannerText = self.tr("Fix the conflicts among the uncommitted changes.")

        # Set up Banner
        if bannerText:
            self.mergeBanner.popUp(bannerTitle, bannerText, heeded=bannerHeeded, canDismiss=False,
                                   buttonLabel=bannerAction, buttonCallback=bannerCallback)
        else:
            self.mergeBanner.setVisible(False)

        if settings.prefs.debug_showPID:
            chain = []
            if DEVDEBUG:
                chain.append("DEVDEBUG")
            elif __debug__:
                chain.append("debug")
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
        self.refreshRepo(task.effects(), task.jumpTo)

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
        message = self.tr("Repository folder went missing:") + "\n" + escamp(self.pathPending)

        # Unload the repo
        self.cleanup(message=message, allowAutoReload=False)

        # Surround repo name with parentheses in tab widget and title bar
        self.nameChange.emit()

    def refreshPrefs(self):
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
            self.openRepo.emit(url.toLocalFile())
            return

        if url.scheme() != APP_URL_SCHEME:
            logger.warning(f"Unsupported scheme in internal link: {url.toDisplayString()}")
            return

        logger.info(f"Internal link: {url.toDisplayString()}")

        if url.authority() == NavLocator.URL_AUTHORITY:
            locator = NavLocator.parseUrl(url)
            self.jump(locator)
        elif url.authority() == "refresh":
            self.refreshRepo()
        elif url.authority() == "opensubfolder":
            p = url.path()
            p = p.removeprefix("/")
            p = os.path.join(self.repo.workdir, p)
            self.openRepo.emit(p)
        elif url.authority() == "prefs":
            p = url.path().removeprefix("/")
            self.openPrefs.emit(p)
        elif url.authority() == "exec":
            query = QUrlQuery(url)
            allqi = query.queryItems(QUrl.ComponentFormattingOption.FullyDecoded)
            cmdName = url.path().removeprefix("/")
            taskClass = tasks.__dict__[cmdName]
            kwargs = {k: v for k, v in allqi}
            self.runTask(taskClass, **kwargs)
        else:
            logger.warning(f"Unsupported authority in internal link: {url.toDisplayString()}")

    # -------------------------------------------------------------------------

    @property
    def _fileStackPageValues(self):
        return typing.get_args(FileStackPage)

    def fileStackPage(self) -> FileStackPage:
        return self._fileStackPageValues[self.filesStack.currentIndex()]

    def setFileStackPage(self, p: FileStackPage):
        self.filesStack.setCurrentIndex(self._fileStackPageValues.index(p))

    @property
    def _diffStackPageValues(self):
        return typing.get_args(DiffStackPage)

    def diffStackPage(self) -> DiffStackPage:
        return self._diffStackPageValues[self.diffStack.currentIndex()]

    def setDiffStackPage(self, p: DiffStackPage):
        self.diffStack.setCurrentIndex(self._diffStackPageValues.index(p))
