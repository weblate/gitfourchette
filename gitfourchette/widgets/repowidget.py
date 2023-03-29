from gitfourchette import log
from gitfourchette import porcelain
from gitfourchette import settings
from gitfourchette import tasks
from gitfourchette import tempdir
from gitfourchette.benchmark import Benchmark
from gitfourchette.nav import NavHistory, NavLocator, NavContext
from gitfourchette.qt import *
from gitfourchette.repostate import RepoState
from gitfourchette.tasks import TaskEffects
from gitfourchette.trash import Trash
from gitfourchette.util import (excMessageBox, excStrings, QSignalBlockerContext, shortHash,
                                showWarning, showInformation, askConfirmation, stockIcon,
                                paragraphs, NonCriticalOperation, tweakWidgetFont,
                                openFolder, openInTextEditor, openInMergeTool, dumpTempBlob,
                                onAppThread)
from gitfourchette.widgets.brandeddialog import showTextInputDialog
from gitfourchette.widgets.conflictview import ConflictView
from gitfourchette.widgets.diffmodel import DiffModel, DiffModelError, DiffConflict, DiffImagePair, ShouldDisplayPatchAsImageDiff
from gitfourchette.widgets.diffview import DiffView
from gitfourchette.widgets.filelist import FileList, DirtyFiles, StagedFiles, CommittedFiles, FileListModel
from gitfourchette.widgets.graphview import GraphView, CommitLogModel
from gitfourchette.widgets.pushdialog import PushDialog
from gitfourchette.widgets.qelidedlabel import QElidedLabel
from gitfourchette.widgets.repostatusdisplay import RepoStatusDisplay, RepoStatusDisplayCache
from gitfourchette.widgets.richdiffview import RichDiffView
from gitfourchette.widgets.searchbar import SearchBar
from gitfourchette.widgets.sidebar import Sidebar
from gitfourchette.unmergedconflict import UnmergedConflict
from html import escape
from typing import Generator, Literal, Type, Callable
import os
import pygit2

TAG = "RepoWidget"


class RepoWidget(QWidget):
    nameChange: Signal = Signal()
    openRepo = Signal(str)

    state: RepoState
    pathPending: str | None  # path of the repository if it isn't loaded yet (state=None)

    navLocator: NavLocator
    navHistory: NavHistory

    @property
    def repo(self) -> pygit2.Repository:
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

    def __init__(self, parent, sharedSplitterStates=None):
        super().__init__(parent)

        self.setObjectName("RepoWidget")

        # Use RepoTaskRunner to schedule operations on the repository
        # to run on a thread separate from the UI thread.
        self.repoTaskRunner = tasks.RepoTaskRunner(self)
        self.repoTaskRunner.refreshPostTask.connect(self.refreshPostTask)
        self.repoTaskRunner.progress.connect(self.onRepoTaskProgress)

        self.state = None
        self.pathPending = None

        self.statusDisplayCache = RepoStatusDisplayCache(self)
        self.statusDisplayCache.setStatus(self.tr("Opening repository..."), True)

        self.busyCursorDelayer = QTimer(self)
        self.busyCursorDelayer.setSingleShot(True)
        self.busyCursorDelayer.setInterval(100)
        self.busyCursorDelayer.timeout.connect(lambda: self.setCursor(Qt.CursorShape.BusyCursor))

        self.navLocator = NavLocator()
        self.navHistory = NavHistory()

        self.sidebar = Sidebar(self)
        self.graphView = GraphView(self)
        self.filesStack = QStackedWidget()
        self.diffStack = QStackedWidget()
        self.committedFiles = CommittedFiles(self)
        self.dirtyFiles = DirtyFiles(self)
        self.stagedFiles = StagedFiles(self)
        self.diffView = DiffView(self)
        self.richDiffView = RichDiffView(self)
        self.conflictView = ConflictView(self)

        self.richDiffView.anchorClicked.connect(self.processInternalLink)
        self.graphView.linkActivated.connect(self.processInternalLink)

        for fileList in [self.dirtyFiles, self.stagedFiles, self.committedFiles]:
            # File list view selections are mutually exclusive.
            for otherFileList in [self.dirtyFiles, self.stagedFiles, self.committedFiles]:
                if fileList != otherFileList:
                    fileList.jump.connect(otherFileList.clearSelectionSilently)
            fileList.nothingClicked.connect(self.clearDiffView)

        self.committedFiles.openDiffInNewWindow.connect(self.loadPatchInNewWindow)

        self.conflictView.openFile.connect(self.openConflictFile)
        self.conflictView.openMergeTool.connect(self.openConflictInMergeTool)

        self.sidebar.commitClicked.connect(self.graphView.selectCommit)
        self.sidebar.pushBranch.connect(self.startPushFlow)
        self.sidebar.refClicked.connect(self.selectRef)
        self.sidebar.uncommittedChangesClicked.connect(self.graphView.selectUncommittedChanges)
        self.sidebar.toggleHideBranch.connect(self.toggleHideBranch)
        self.sidebar.openSubmoduleRepo.connect(self.openSubmoduleRepo)
        self.sidebar.openSubmoduleFolder.connect(self.openSubmoduleFolder)

        # ----------------------------------

        self.splitterStates = sharedSplitterStates or {}

        self.dirtyHeader = QElidedLabel(self.tr("Loading dirty files..."))
        self.stagedHeader = QElidedLabel(self.tr("Loading staged files..."))
        self.committedHeader = QElidedLabel(" ")
        self.diffHeader = QElidedLabel(" ")
        self.diffHeader.setElideMode(Qt.TextElideMode.ElideMiddle)
        self.diffHeader.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        for headerLabel in self.dirtyHeader, self.stagedHeader, self.diffHeader, self.committedHeader:
            tweakWidgetFont(headerLabel, 90)

        dirtyContainer = QWidget()
        dirtyContainer.setLayout(QVBoxLayout())
        dirtyContainer.layout().setSpacing(1)
        dirtyContainer.layout().setContentsMargins(0, 0, 0, 0)
        dirtyContainer.layout().addWidget(self.dirtyHeader)
        dirtyContainer.layout().addWidget(self.dirtyFiles)
        stageContainer = QWidget()
        stageContainer.setLayout(QVBoxLayout())
        stageContainer.layout().setContentsMargins(0, 0, 0, 0)
        stageContainer.layout().setSpacing(1)
        stageContainer.layout().addWidget(self.stagedHeader)
        stageContainer.layout().addWidget(self.stagedFiles)
        commitButtonsContainer = QWidget()
        commitButtonsContainer.setLayout(QHBoxLayout())
        commitButtonsContainer.layout().setContentsMargins(0, 0, 0, 0)
        stageContainer.layout().addWidget(commitButtonsContainer)
        self.commitButton = QPushButton(self.tr("&Commit"))
        self.amendButton = QPushButton(self.tr("&Amend"))
        commitButtonsContainer.layout().addWidget(self.commitButton)
        commitButtonsContainer.layout().addWidget(self.amendButton)
        self.stageSplitter = QSplitter(Qt.Orientation.Vertical)
        self.stageSplitter.addWidget(dirtyContainer)
        self.stageSplitter.addWidget(stageContainer)

        self.dirtyHeader.setBuddy(self.dirtyFiles)
        self.stagedHeader.setBuddy(self.stagedFiles)

        self.committedFilesContainer = QWidget()
        self.committedFilesContainer.setLayout(QVBoxLayout())
        self.committedFilesContainer.layout().setContentsMargins(0,0,0,0)
        self.committedFilesContainer.layout().setSpacing(1)
        self.committedFilesContainer.layout().addWidget(self.committedHeader)
        self.committedFilesContainer.layout().addWidget(self.committedFiles)

        self.filesStack.addWidget(self.committedFilesContainer)
        self.filesStack.addWidget(self.stageSplitter)
        self.filesStack.setCurrentWidget(self.committedFilesContainer)

        self.diffStack.addWidget(self.diffView)
        self.diffStack.addWidget(self.richDiffView)
        self.diffStack.addWidget(self.conflictView)
        self.diffStack.setCurrentWidget(self.diffView)

        diffViewContainer = QWidget()
        diffViewContainer.setLayout(QVBoxLayout())
        diffViewContainer.layout().setContentsMargins(0,0,0,0)
        diffViewContainer.layout().setSpacing(1)
        diffViewContainer.layout().addWidget(self.diffHeader)
        diffViewContainer.layout().addWidget(self.diffStack)

        bottomSplitter = QSplitter(Qt.Orientation.Horizontal)
        bottomSplitter.addWidget(self.filesStack)
        bottomSplitter.addWidget(diffViewContainer)
        bottomSplitter.setSizes([100, 300])

        mainSplitter = QSplitter(Qt.Orientation.Vertical)
        mainSplitter.addWidget(self.graphView)
        mainSplitter.addWidget(bottomSplitter)
        mainSplitter.setSizes([100, 150])

        sideSplitter = QSplitter(Qt.Orientation.Horizontal)
        sideSplitter.addWidget(self.sidebar)
        sideSplitter.addWidget(mainSplitter)
        sideSplitter.setSizes([100, 500])
        sideSplitter.setStretchFactor(0, 0)  # don't auto-stretch sidebar when resizing window
        sideSplitter.setStretchFactor(1, 1)

        self.setLayout(QVBoxLayout())
        self.layout().setSpacing(0)
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().addWidget(sideSplitter)

        # object names are required for state saving to work
        mainSplitter.setObjectName("MainSplitter")
        bottomSplitter.setObjectName("BottomSplitter")
        self.stageSplitter.setObjectName("StageSplitter")
        sideSplitter.setObjectName("SideSplitter")
        self.splittersToSave = [mainSplitter, bottomSplitter, self.stageSplitter, sideSplitter]
        # save splitter state in splitterMoved signal
        for splitter in self.splittersToSave:
            splitter.splitterMoved.connect(lambda pos, index, splitter=splitter: self.saveSplitterState(splitter))

        # remove frames for a cleaner look
        #for w in self.graphView, self.diffView, self.dirtyView, self.stageView, self.changedFilesView, self.sidebar:
        #    w.setFrameStyle(QFrame.Shape.NoFrame)
        self.sidebar.setFrameStyle(QFrame.Shape.NoFrame)

        # ----------------------------------
        # Connect signals to async tasks

        self.connectTask(self.amendButton.clicked,              tasks.AmendCommit, argc=0)
        self.connectTask(self.commitButton.clicked,             tasks.NewCommit, argc=0)
        self.connectTask(self.committedFiles.jump,              tasks.Jump)
        self.connectTask(self.conflictView.hardSolve,           tasks.HardSolveConflict)
        self.connectTask(self.conflictView.markSolved,          tasks.MarkConflictSolved)
        self.connectTask(self.diffView.applyPatch,              tasks.ApplyPatch)
        self.connectTask(self.diffView.revertPatch,             tasks.RevertPatch)
        self.connectTask(self.dirtyFiles.discardFiles,          tasks.DiscardFiles)
        self.connectTask(self.dirtyFiles.jump,                  tasks.Jump)
        self.connectTask(self.dirtyFiles.stageFiles,            tasks.StageFiles)
        self.connectTask(self.dirtyFiles.stashFiles,            tasks.NewStash)
        self.connectTask(self.graphView.amendChanges,           tasks.AmendCommit)
        self.connectTask(self.graphView.checkoutCommit,         tasks.CheckoutCommit)
        self.connectTask(self.graphView.cherrypickCommit,       tasks.CherrypickCommit)
        self.connectTask(self.graphView.commitChanges,          tasks.NewCommit)
        self.connectTask(self.graphView.exportCommitAsPatch,    tasks.ExportCommitAsPatch)
        self.connectTask(self.graphView.exportWorkdirAsPatch,   tasks.ExportWorkdirAsPatch)
        self.connectTask(self.graphView.jump,                   tasks.Jump)
        self.connectTask(self.graphView.newBranchFromCommit,    tasks.NewBranchFromCommit)
        self.connectTask(self.graphView.newStash,               tasks.NewStash)
        self.connectTask(self.graphView.newTagOnCommit,         tasks.NewTag)
        self.connectTask(self.graphView.resetHead,              tasks.ResetHead)
        self.connectTask(self.graphView.revertCommit,           tasks.RevertCommit)
        self.connectTask(self.sidebar.amendChanges,             tasks.AmendCommit)
        self.connectTask(self.sidebar.applyStash,               tasks.ApplyStash)
        self.connectTask(self.sidebar.commitChanges,            tasks.NewCommit)
        self.connectTask(self.sidebar.deleteBranch,             tasks.DeleteBranch)
        self.connectTask(self.sidebar.deleteRemote,             tasks.DeleteRemote)
        self.connectTask(self.sidebar.deleteRemoteBranch,       tasks.DeleteRemoteBranch)
        self.connectTask(self.sidebar.dropStash,                tasks.DropStash)
        self.connectTask(self.sidebar.editRemote,               tasks.EditRemote)
        self.connectTask(self.sidebar.editTrackingBranch,       tasks.EditTrackedBranch)
        self.connectTask(self.sidebar.exportStashAsPatch,       tasks.ExportStashAsPatch)
        self.connectTask(self.sidebar.exportWorkdirAsPatch,     tasks.ExportWorkdirAsPatch)
        self.connectTask(self.sidebar.fastForwardBranch,        tasks.FastForwardBranch)
        self.connectTask(self.sidebar.fetchRemote,              tasks.FetchRemote)
        self.connectTask(self.sidebar.fetchRemoteBranch,        tasks.FetchRemoteBranch)
        self.connectTask(self.sidebar.newBranch,                tasks.NewBranchFromHead)
        self.connectTask(self.sidebar.newBranchFromLocalBranch, tasks.NewBranchFromLocalBranch)
        self.connectTask(self.sidebar.newRemote,                tasks.NewRemote)
        self.connectTask(self.sidebar.newStash,                 tasks.NewStash)
        self.connectTask(self.sidebar.newTrackingBranch,        tasks.NewTrackingBranch)
        self.connectTask(self.sidebar.renameBranch,             tasks.RenameBranch)
        self.connectTask(self.sidebar.renameRemoteBranch,       tasks.RenameRemoteBranch)
        self.connectTask(self.sidebar.switchToBranch,           tasks.SwitchBranch)
        self.connectTask(self.stagedFiles.jump,                 tasks.Jump)
        self.connectTask(self.stagedFiles.stashFiles,           tasks.NewStash)
        self.connectTask(self.stagedFiles.unstageFiles,         tasks.UnstageFiles)

    # -------------------------------------------------------------------------

    def initTask(self, taskClass: Type[tasks.RepoTask]):
        task = taskClass(self.repoTaskRunner)
        task.setRepo(self.repo)
        return task

    def runTask(self, taskClass: Type[tasks.RepoTask], *args, **kwargs):
        task = self.initTask(taskClass)
        QTimer.singleShot(0, lambda: self.repoTaskRunner.put(task, *args, **kwargs))
        return task

    def connectTask(self, signal: Signal, taskClass: Type[tasks.RepoTask], argc: int = -1, preamble: Callable = None):
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

    def saveSplitterState(self, splitter: QSplitter):
        self.splitterStates[splitter.objectName()] = splitter.saveState()

    def restoreSplitterStates(self):
        for splitter in self.splittersToSave:
            try:
                splitter.restoreState(self.splitterStates[splitter.objectName()])
            except KeyError:
                pass

    # -------------------------------------------------------------------------

    def saveFilePositions(self):
        dc = 0
        ds = 0
        if self.diffStack.currentWidget() == self.diffView:
            if not self.diffView.currentLocator.isSimilarEnoughTo(self.navLocator):
                log.warning(TAG, f"RepoWidget/DiffView locator mismatch: {self.navLocator} vs. ({self.diffView.currentLocator})")
            dc = self.diffView.textCursor().position()
            ds = self.diffView.verticalScrollBar().value()

        self.navLocator = NavLocator(
            context=self.navLocator.context,
            commit=self.navLocator.commit,
            path=self.navLocator.path,
            diffCursor=dc,
            diffScroll=ds)

        self.navHistory.push(self.navLocator)

        return self.navLocator

    def restoreSelectedFile(self, locator: NavLocator):
        # TODO: This should probably go

        if locator.context.isDirty():
            fl = self.dirtyFiles
        elif locator.context == NavContext.STAGED:
            fl = self.stagedFiles
        elif locator.context == NavContext.COMMITTED:
            fl = self.committedFiles
        else:
            return False

        fl.clearSelectionSilently()
        if fl.selectFile(locator.path):
            # self.curLocator = locator  #? loadpatch should do this?
            # self.navHistory.push(locator)
            return True
        else:
            return False

    def restoreDiffPosition(self, locator: NavLocator):
        cursorPosition = locator.diffCursor
        scrollPosition = locator.diffScroll

        newTextCursor = QTextCursor(self.diffView.textCursor())
        newTextCursor.setPosition(cursorPosition)
        self.diffView.setTextCursor(newTextCursor)

        self.diffView.verticalScrollBar().setValue(scrollPosition)

    def jump(self, locator: NavLocator):
        self.runTask(tasks.Jump, locator)

    def navigateBack(self):
        self.runTask(tasks.JumpBackOrForward, -1)

    def navigateForward(self):
        self.runTask(tasks.JumpBackOrForward, 1)

    # -------------------------------------------------------------------------

    def selectNextFile(self, down=True):
        if self.filesStack.currentWidget() == self.committedFilesContainer:
            widgets = [self.committedFiles]
        elif self.filesStack.currentWidget() == self.stageSplitter:
            widgets = [self.dirtyFiles, self.stagedFiles]
        else:
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
            widgets[leader].clearSelectionSilently()
            widgets[leader].selectRow(row)
        else:
            QApplication.beep()

    # -------------------------------------------------------------------------

    def getTitle(self):
        if self.state:
            return self.state.shortName
        elif self.pathPending:
            return F"({settings.history.getRepoNickname(self.pathPending)})"
        else:
            return "???"

    def closeEvent(self, event: QCloseEvent):
        """ Called when closing a repo tab """
        self.cleanup()

    def cleanup(self):
        assert onAppThread()

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

        if self.state and self.state.repo:
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

    def clearDiffView(self):
        self.diffView.clear()
        self.diffStack.setCurrentWidget(self.diffView)
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

        self.filesStack.setCurrentWidget(self.stageSplitter)
        self.committedFiles.clear()

        self.clearDiffView()

    def loadPatchInNewWindow(self, patch: pygit2.Patch, locator: NavLocator):
        with NonCriticalOperation(self.tr("Load diff in new window")):
            diffWindow = DiffView(self)
            diffWindow.replaceDocument(self.repo, patch, locator, DiffModel.fromPatch(patch))
            diffWindow.resize(550, 700)
            diffWindow.setWindowTitle(locator.asTitle())
            diffWindow.setWindowFlag(Qt.WindowType.Window, True)
            diffWindow.setFrameStyle(QFrame.Shape.NoFrame)
            diffWindow.show()

    def startPushFlow(self, branchName: str = ""):
        pushDialog = PushDialog.startPushFlow(self, self.repo, self.repoTaskRunner, branchName)

    def openSubmoduleRepo(self, submoduleKey: str):
        path = porcelain.getSubmoduleWorkdir(self.repo, submoduleKey)
        self.openRepo.emit(path)

    def openSubmoduleFolder(self, submoduleKey: str):
        path = porcelain.getSubmoduleWorkdir(self.repo, submoduleKey)
        openFolder(path)

    # -------------------------------------------------------------------------
    # Conflicts

    def openConflictFile(self, path: str):
        fullPath = porcelain.workdirPath(self.repo, path)
        openInTextEditor(self, fullPath)

    def openConflictInMergeTool(self, conflict: DiffConflict):
        umc = UnmergedConflict(self, self.repo, conflict)
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

    # -------------------------------------------------------------------------

    @property
    def isWorkdirShown(self):
        return self.filesStack.currentWidget() == self.stageSplitter

    def refreshRepo(self, flags: TaskEffects = TaskEffects.DefaultRefresh):
        if not self.state:
            return

        if flags == TaskEffects.Nothing:
            return

        if flags & TaskEffects.Workdir:
            self.state.workdirStale = True

        self.runTask(tasks.RefreshRepo, flags)

    def onRegainFocus(self):
        if not self.state:
            return

        if self.isVisible() and tasks.RefreshRepo.canKill_static(self.repoTaskRunner.currentTask):
            QTimer.singleShot(0, lambda: self.refreshRepo(TaskEffects.DefaultRefresh | TaskEffects.Workdir))
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
            oid = porcelain.getHeadCommitOid(repo)
            inBrackets = self.tr("detached HEAD @ {0}").format(shortHash(oid))
        else:
            inBrackets = porcelain.getActiveBranchShorthand(repo)

        if repo and repo.index.conflicts:
            inBrackets += ", \u26a0 "
            inBrackets += self.tr("merge conflict")
            self.statusDisplayCache.setWarning(self.tr("merge conflict in workdir"))
        else:
            self.statusDisplayCache.setWarning()

        if settings.prefs.debug_showPID:
            suffix += qAppName()
            if __debug__:
                suffix += "-debug"
            suffix += F" PID {os.getpid()}, {qtBindingName}"

        if suffix:
            suffix = " \u2013 " + suffix

        if inBrackets:
            suffix = F" [{inBrackets}]{suffix}"

        self.window().setWindowTitle(shortname + suffix)

    # -------------------------------------------------------------------------

    def selectRef(self, refName: str):
        oid = porcelain.getCommitOidFromReferenceName(self.repo, refName)
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

    def recallCommit(self):
        self.runTask(tasks.RecallCommit)

    # -------------------------------------------------------------------------

    def setUpRepoIdentity(self):
        self.runTask(tasks.SetUpRepoIdentity)

    # -------------------------------------------------------------------------

    def refreshPostTask(self, task: tasks.RepoTask):
        self.refreshRepo(task.effects())

    def onRepoTaskProgress(self, progressText: str, withSpinner: bool = False):
        self.statusDisplayCache.status = progressText
        self.statusDisplayCache.spinning = withSpinner
        self.statusDisplayCache.updated.emit(self.statusDisplayCache)

        if not withSpinner:
            self.busyCursorDelayer.stop()
            self.setCursor(Qt.CursorShape.ArrowCursor)
        elif not self.busyCursorDelayer.isActive():
            self.busyCursorDelayer.start()

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

        if url.scheme() != APP_URL_SCHEME:
            log.warning(TAG, "Unsupported scheme in internal link:", url.toDisplayString())
            return

        log.info(TAG, F"Internal link:", url.toDisplayString())

        if url.authority() == NavLocator.URL_AUTHORITY:
            locator = NavLocator.parseUrl(url)
            self.jump(locator)
        elif url.authority() == "refresh":
            self.refreshRepo()
        else:
            log.warning(TAG, "Unsupported authority in internal link: ", url.toDisplayString())
