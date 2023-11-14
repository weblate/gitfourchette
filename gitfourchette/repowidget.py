import contextlib
import typing
from typing import Literal, Type

from gitfourchette import log
from gitfourchette import settings
from gitfourchette import tasks
from gitfourchette.diffview.diffdocument import DiffDocument
from gitfourchette.diffview.diffview import DiffView
from gitfourchette.diffview.specialdiff import DiffConflict
from gitfourchette.diffview.specialdiffview import SpecialDiffView
from gitfourchette.filelists.committedfiles import CommittedFiles
from gitfourchette.filelists.dirtyfiles import DirtyFiles
from gitfourchette.filelists.filelist import FileList
from gitfourchette.filelists.stagedfiles import StagedFiles
from gitfourchette.forms.brandeddialog import showTextInputDialog
from gitfourchette.forms.conflictview import ConflictView
from gitfourchette.forms.pushdialog import PushDialog
from gitfourchette.globalshortcuts import GlobalShortcuts
from gitfourchette.graphview.graphview import GraphView
from gitfourchette.nav import NavHistory, NavLocator, NavContext
from gitfourchette.porcelain import *
from gitfourchette.qt import *
from gitfourchette.repostate import RepoState
from gitfourchette.sidebar.sidebar import Sidebar
from gitfourchette.tasks import TaskEffects, TaskBook
from gitfourchette.toolbox import *
from gitfourchette.trash import Trash
from gitfourchette.unmergedconflict import UnmergedConflict

TAG = "RepoWidget"

FileStackPage = Literal["workdir", "commit"]
DiffStackPage = Literal["text", "special", "conflict"]


class RepoWidget(QWidget):
    nameChange = Signal()
    openRepo = Signal(str)
    openPrefs = Signal(str)

    busyMessage = Signal(str)
    statusMessage = Signal(str)
    clearStatus = Signal()
    statusWarning = Signal(str)

    state: RepoState | None

    pathPending: str
    "Path of the repository if it isn't loaded yet (state=None)"

    navLocator: NavLocator
    navHistory: NavHistory

    splittersToSave: list[QSplitter]
    splitterStates: dict[str, QByteArray]

    @property
    def repo(self) -> Repo:
        return self.state.repo

    @property
    def isLoaded(self):
        return self.state is not None

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

        self.busyCursorDelayer = QTimer(self)
        self.busyCursorDelayer.setSingleShot(True)
        self.busyCursorDelayer.setInterval(100)
        self.busyCursorDelayer.timeout.connect(lambda: self.setCursor(Qt.CursorShape.BusyCursor))

        self.navLocator = NavLocator()
        self.navHistory = NavHistory()

        # ----------------------------------
        # Build widgets

        self.sidebar = Sidebar(self)
        self.graphView = GraphView(self)
        self.filesStack = self._makeFilesStack()
        diffViewContainer = self._makeDiffContainer()

        # ----------------------------------
        # Splitters

        bottomSplitter = QSplitter(Qt.Orientation.Horizontal)
        bottomSplitter.setObjectName("BottomSplitter")
        bottomSplitter.addWidget(self.filesStack)
        bottomSplitter.addWidget(diffViewContainer)
        bottomSplitter.setSizes([100, 300])

        mainSplitter = QSplitter(Qt.Orientation.Vertical)
        mainSplitter.setObjectName("MainSplitter")
        mainSplitter.addWidget(self.graphView)
        mainSplitter.addWidget(bottomSplitter)
        mainSplitter.setSizes([100, 150])

        sideSplitter = QSplitter(Qt.Orientation.Horizontal)
        sideSplitter.setObjectName("SideSplitter")
        sideSplitter.addWidget(self.sidebar)
        sideSplitter.addWidget(mainSplitter)
        sideSplitter.setSizes([100, 500])
        sideSplitter.setStretchFactor(0, 0)  # don't auto-stretch sidebar when resizing window
        sideSplitter.setStretchFactor(1, 1)

        mainLayout = QVBoxLayout()
        mainLayout.setSpacing(0)
        mainLayout.setContentsMargins(0, 0, 0, 0)
        mainLayout.addWidget(sideSplitter)
        self.setLayout(mainLayout)

        self.splitterStates = {}

        splitters = self.findChildren(QSplitter)
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

        self.diffView.contextualHelp.connect(self.statusMessage)

        self.specialDiffView.anchorClicked.connect(self.processInternalLink)
        self.graphView.linkActivated.connect(self.processInternalLink)

        self.committedFiles.openDiffInNewWindow.connect(self.loadPatchInNewWindow)

        self.conflictView.openMergeTool.connect(self.openConflictInMergeTool)
        self.conflictView.openPrefs.connect(self.openPrefs)
        self.conflictView.linkActivated.connect(self.processInternalLink)

        self.sidebar.commitClicked.connect(self.graphView.selectCommit)
        self.sidebar.pushBranch.connect(self.startPushFlow)
        self.sidebar.refClicked.connect(self.selectRef)
        self.sidebar.uncommittedChangesClicked.connect(self.graphView.selectUncommittedChanges)
        self.sidebar.toggleHideBranch.connect(self.toggleHideBranch)
        self.sidebar.toggleHideStash.connect(self.toggleHideStash)
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

        filesStack = QStackedWidget()
        filesStack.addWidget(workdirSplitter)
        filesStack.addWidget(committedFilesContainer)

        return filesStack

    def _makeDirtyContainer(self):
        header = QElidedLabel(" ")

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
        layout.addWidget(dirtyFiles, 1, 0, 1, 2)

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
        layout.addWidget(stagedFiles, 1, 0, 1, 2)
        layout.addWidget(commitButtonsStack, 2, 0, 1, 2)
        layout.setRowStretch(1, 100)
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
        layout.addWidget(committedFiles)

        container = QWidget()
        container.setLayout(layout)

        self.committedFiles = committedFiles
        self.committedHeader = header
        return container

    def _makeDiffContainer(self):
        header = QElidedLabel(" ")
        header.setElideMode(Qt.TextElideMode.ElideMiddle)
        header.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        header.setMinimumHeight(24)

        diff = DiffView()

        specialDiff = SpecialDiffView()

        conflict = ConflictView()
        conflictScroll = QScrollArea()
        conflictScroll.setWidget(conflict)
        conflictScroll.setWidgetResizable(True)

        stack = QStackedWidget()
        # Add widgets in same order as DiffStackPage
        stack.addWidget(diff)
        stack.addWidget(specialDiff)
        stack.addWidget(conflictScroll)
        stack.setCurrentWidget(diff)

        layout = QVBoxLayout()
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(1)
        layout.addWidget(header)
        layout.addWidget(stack)

        container = QWidget()
        container.setLayout(layout)

        self.diffHeader = header
        self.diffStack = stack
        self.conflictView = conflict
        self.specialDiffView = specialDiff
        self.diffView = diff

        return container

    # -------------------------------------------------------------------------
    # Tasks

    def initTask(self, taskClass: Type[tasks.RepoTask]):
        assert issubclass(taskClass, tasks.RepoTask)
        task = taskClass(self.repoTaskRunner)
        task.setRepo(self.repo)
        return task

    def runTask(self, taskClass: Type[tasks.RepoTask], *args, **kwargs):
        task = self.initTask(taskClass)
        self.repoTaskRunner.put(task, *args, **kwargs)
        return task

    def connectTask(self, signal: Signal, taskClass: Type[tasks.RepoTask], argc: int = -1):
        def createTask(*args):
            if argc >= 0:
                args = args[:argc]
            return self.runTask(taskClass, *args)
        signal.connect(createTask)

    def setRepoState(self, state: RepoState):
        if state:
            self.state = state
        else:
            self.state = None

    # -------------------------------------------------------------------------
    # Splitter state

    def setSharedSplitterState(self, splitterStates: dict[str, QByteArray]):
        self.splitterStates = splitterStates
        self.restoreSplitterStates()

    def saveSplitterState(self, splitter: QSplitter):
        name = splitter.objectName()
        state = splitter.saveState()
        self.splitterStates[name] = state

    def restoreSplitterStates(self):
        for splitter in self.splittersToSave:
            with contextlib.suppress(KeyError):
                name = splitter.objectName()
                state = self.splitterStates[name]
                splitter.restoreState(state)
            splitter.setHandleWidth(-1)  # reset default splitter width

    # -------------------------------------------------------------------------

    def saveFilePositions(self):
        if self.diffStack.currentWidget() is self.diffView:
            newLocator = self.diffView.getPreciseLocator()
            if not newLocator.isSimilarEnoughTo(self.navLocator):
                log.warning(TAG, f"RepoWidget/DiffView locator mismatch: {self.navLocator} vs. {newLocator}")
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
            log.warning(TAG, f"Unknown FileStackPage {page})")
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
            QApplication.beep()

    # -------------------------------------------------------------------------

    def __repr__(self):
        return f"RepoWidget({self.getTitle()})"

    def getTitle(self):
        if self.state:
            return self.state.shortName
        elif self.pathPending:
            name = settings.history.getRepoTabName(self.pathPending)
            return f"({name})"
        else:
            return "???"

    def closeEvent(self, event: QCloseEvent):
        """ Called when closing a repo tab """
        self.cleanup()

    def cleanup(self):
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
                log.warning(TAG, f"IOError when writing prefs: {e}")

        # Clear UI
        with QSignalBlockerContext(
                self.committedFiles, self.dirtyFiles, self.stagedFiles,
                self.graphView, self.sidebar):
            self.setEnabled(False)
            self.committedFiles.clear()
            self.dirtyFiles.clear()
            self.stagedFiles.clear()
            self.graphView.clear()
            self.clearDiffView()
            self.sidebar.model().clear()

        if hasRepo:
            # Save path if we want to reload the repo later
            self.pathPending = os.path.normpath(self.state.repo.workdir)

            # Kill any ongoing task then block UI thread until the task dies cleanly
            self.repoTaskRunner.killCurrentTask()
            self.repoTaskRunner.joinZombieTask()

            # Free the repository
            self.state.repo.free()
            self.state.repo = None
            log.info(TAG, "Repository freed:", self.pathPending)

        self.setRepoState(None)

        # Clean up status bar if there were repo-specific warnings in it
        self.refreshWindowTitle()

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
        showTextInputDialog(
            self,
            self.tr("Edit repo nickname"),
            self.tr("Enter new nickname for repo, or enter blank line to reset:"),
            settings.history.getRepoNickname(self.workdir),
            onAccept,
            okButtonText=self.tr("Rename", "edit repo nickname"))

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
        umc = UnmergedConflict(self, self.repo, conflict)
        umc.mergeComplete.connect(lambda: self.runTask(tasks.AcceptMergeConflictResolution, umc))
        umc.startProcess()

    # -------------------------------------------------------------------------
    # Entry point for generic "Find" command

    def dispatchSearchCommand(self, op: Literal["start", "next", "previous"]):
        diffSearchWidgets = (self.dirtyFiles, self.stagedFiles, self.committedFiles,
                             self.diffView, self.diffView.searchBar.ui.lineEdit)

        if self.diffView.isVisibleTo(self) and any(w.hasFocus() for w in diffSearchWidgets):
            self.diffView.search(op)
        else:
            self.graphView.search(op)

    # -------------------------------------------------------------------------

    def toggleHideBranch(self, branchName: str):
        assert branchName.startswith("refs/")
        self.state.toggleHideBranch(branchName)
        self.graphView.setHiddenCommits(self.state.hiddenCommits)

    def toggleHideStash(self, stashOid: Oid):
        self.state.toggleHideStash(stashOid)
        self.graphView.setHiddenCommits(self.state.hiddenCommits)

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

        if not self.state:
            return

        if self.isVisible() and not self.repoTaskRunner.isBusy():
            self.refreshRepo(TaskEffects.DefaultRefresh | TaskEffects.Workdir)
        else:
            self.state.workdirStale = True

    def refreshWindowTitle(self):
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
            inBrackets = repo.head_branch_shorthand

        if repo and repo.any_conflicts:
            inBrackets += ", \u26a0 "
            inBrackets += self.tr("merge conflict")
            self.statusWarning.emit(self.tr("merge conflict in workdir"))
        else:
            self.statusWarning.emit("")

        if settings.prefs.debug_showPID:
            suffix += qAppName()
            if __debug__:
                suffix += "-debug"
            suffix += F" (PID {os.getpid()}, {qtBindingName}"
            if settings.TEST_MODE:
                suffix += ", TEST_MODE"
            if settings.SYNC_TASKS:
                suffix += ", SYNC_TASKS"
            suffix += ")"

        if suffix:
            suffix = " \u2013 " + suffix

        if inBrackets:
            suffix = F" [{inBrackets}]{suffix}"

        self.window().setWindowTitle(shortname + suffix)

    # -------------------------------------------------------------------------

    def selectRef(self, refName: str):
        oid = self.repo.get_commit_oid_from_refname(refName)
        self.jump(NavLocator(NavContext.COMMITTED, commit=oid))

    # -------------------------------------------------------------------------

    def openRescueFolder(self):
        trash = Trash(self.repo)
        if trash.exists():
            openFolder(trash.trashDir)
        else:
            showInformation(
                self,
                self.tr("Open Rescue Folder"),
                self.tr("There’s no rescue folder for this repository. Perhaps you haven’t discarded a change with {0} yet.").format(qAppName()))

    def clearRescueFolder(self):
        trash = Trash(self.repo)
        sizeOnDisk, patchCount = trash.getSize()

        if patchCount <= 0:
            showInformation(
                self,
                self.tr("Clear Rescue Folder"),
                self.tr("There are no discarded changes to delete."))
            return

        humanSize = self.locale().formattedDataSize(sizeOnDisk)

        askPrompt = (
            self.tr("Do you want to permanently delete <b>%n</b> discarded patch(es)?", "", patchCount) + "<br>" +
            self.tr("This will free up {0} on disk.").format(humanSize) + "<br>" +
            translate("Global", "This cannot be undone!"))

        askConfirmation(
            parent=self,
            title=self.tr("Clear rescue folder"),
            text=askPrompt,
            callback=lambda: trash.clear(),
            okButtonText=self.tr("Delete permanently"),
            okButtonIcon=stockIcon(QStyle.StandardPixmap.SP_DialogDiscardButton))

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
        # Unload the repo
        self.cleanup()

        # Surround repo name with parentheses in tab widget and title bar
        self.nameChange.emit()

        showWarning(
            self,
            self.tr("Repository folder missing"),
            paragraphs(self.tr("The repository folder has gone missing at this location:"), escape(self.pathPending)))

    def refreshPrefs(self):
        self.diffView.refreshPrefs()
        self.graphView.refreshPrefs()
        self.conflictView.refreshPrefs()

        # Reflect any change in titlebar prefs
        if self.isVisible():
            self.refreshWindowTitle()

    # -------------------------------------------------------------------------

    def processInternalLink(self, url: QUrl | str):
        if not isinstance(url, QUrl):
            url = QUrl(url)

        if url.isLocalFile():
            self.openRepo.emit(url.toLocalFile())
            return

        if url.scheme() != APP_URL_SCHEME:
            log.warning(TAG, "Unsupported scheme in internal link:", url.toDisplayString())
            return

        log.info(TAG, F"Internal link:", url.toDisplayString())

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
            print("taskClass:", taskClass)
            kwargs = {k: v for k, v in allqi}
            self.runTask(taskClass, **kwargs)
        else:
            log.warning(TAG, "Unsupported authority in internal link: ", url.toDisplayString())

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
