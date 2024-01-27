from __future__ import annotations

import enum
import logging
from typing import Any, Generator, Type

from gitfourchette.nav import NavLocator
from gitfourchette.porcelain import Repo, ConflictError, MultiFileError, RepositoryState
from gitfourchette.qt import *
from gitfourchette.toolbox import *

logger = logging.getLogger(__name__)


def showConflictErrorMessage(parent: QWidget, exc: ConflictError, opName="Operation"):
    maxConflicts = 10
    numConflicts = len(exc.conflicts)

    # lupdate doesn't pick up the plural form with translate("Context", "%n", "", numConflicts)
    title = tr("%n conflicting files", "", numConflicts)
    nFilesSubmessage = tr("<b>%n files</b>", "", numConflicts)

    if exc.description == "workdir":
        message = translate("Conflict", "Operation {0} conflicts with {1} in the working directory:"
                            ).format(bquo(opName), nFilesSubmessage)
    elif exc.description == "HEAD":
        message = translate("Conflict", "Operation {0} conflicts with {1} in the commit at HEAD:"
                            ).format(bquo(opName), nFilesSubmessage)
    else:
        message = translate("Conflict", "Operation {0} has caused a conflict with {1} ({2}):"
                            ).format(bquo(opName), nFilesSubmessage, exc.description)

    # TODO: Use ulList?
    message += f"<ul><li>"
    message += "</li><li>".join(exc.conflicts[:maxConflicts])
    if numConflicts > maxConflicts:
        numHidden = numConflicts - maxConflicts
        message += "</li><li><i>"
        message += translate("Conflict",
                             "...and {0} more. Only the first {1} conflicts are shown above; "
                             "click “Show Details” to view all {2} conflicts."
                             ).format(numHidden, maxConflicts, numConflicts)
        message += "</li>"
    message += "</li></ul>"

    if exc.description == "workdir":
        message += translate("Conflict", "Before you try again, you should either "
                                         "commit, stash, or discard your changes.")

    qmb = showWarning(parent, title, message)

    if numConflicts > maxConflicts:
        qmb.setDetailedText("\n".join(exc.conflicts))


class TaskPrereqs(enum.IntFlag):
    Nothing = 0
    NoUnborn = enum.auto()
    NoConflicts = enum.auto()
    NoCherrypick = enum.auto()
    NoStagedChanges = enum.auto()


class TaskEffects(enum.IntFlag):
    """
    Flags indicating which parts of the UI to refresh
    after a task runs to completion.
    """

    Nothing = 0
    "The task doesn't modify the repository."

    Workdir = enum.auto()
    "The task affects indexed and/or unstaged changes."

    Refs = enum.auto()
    "The task affects branches (local or remote), stashes, or tags."

    Remotes = enum.auto()
    "The task affects remotes registered with this repository."

    Head = enum.auto()
    "The task moves HEAD to a different commit."

    ShowWorkdir = enum.auto()
    "Make sure the workdir is visible once the task succeeds."

    DefaultRefresh = Workdir | Refs | Remotes
    "Default flags for RepoWidget.refreshRepo()"


class FlowControlToken(QObject):
    """
    Object that can be yielded from `RepoTask.flow()` to control the flow of the coroutine.
    """

    class Kind(enum.IntEnum):
        CONTINUE_ON_UI_THREAD = enum.auto()
        CONTINUE_ON_WORK_THREAD = enum.auto()
        WAIT_READY = enum.auto()

    ready = Signal()
    flowControl: Kind

    def __init__(self, flowControl: Kind = Kind.CONTINUE_ON_UI_THREAD):
        # DON'T set a parent, because this can be instantiated on an arbitrary thread.
        # (QObject: Cannot create children for a parent that is in a different thread.)
        # Python's GC should take care of deleting the tokens when needed.
        super().__init__(None)
        self.flowControl = flowControl
        self.setObjectName("FlowControlToken")

    def __str__(self):
        return F"FlowControlToken({self.flowControl.name})"


class AbortTask(Exception):
    """ To bail from a coroutine early, we must raise an exception to ensure that
    any active context managers exit deterministically."""
    def __init__(self, text: str = "", icon: MessageBoxIconName = "warning", asStatusMessage: bool = False):
        super().__init__(text)
        self.icon = icon
        self.asStatusMessage = asStatusMessage


class RepoGoneError(FileNotFoundError):
    pass


class RepoTask(QObject):
    """
    Task that manipulates a repository.
    """

    FlowGeneratorType = Generator[FlowControlToken, None, Any]

    _globalTaskCounter = 0

    repo: Repo | None
    taskID: int
    jumpTo: NavLocator | None

    _currentFlow: FlowGeneratorType | None
    _currentIteration: int

    _taskStack: list[RepoTask]
    """Stack of active tasks in the chain of flowSubtask calls, including the root task at index 0.
    The reference to the list object is shared by all tasks in the same flowSubtask chain."""

    @classmethod
    def name(cls) -> str:
        from gitfourchette.tasks.taskbook import TaskBook
        return TaskBook.names.get(cls, cls.__name__)

    @classmethod
    def invoke(cls, *args):
        TaskInvoker.invoke(cls, *args)

    def __init__(self, parent: QObject):
        super().__init__(parent)
        self.repo = None
        self._currentFlow = None
        self._currentIteration = 0
        self.taskID = RepoTask._globalTaskCounter
        RepoTask._globalTaskCounter += 1
        self.setObjectName(f"task{self.__class__.__name__}")
        self.jumpTo = None
        self._taskStack = [self]

    @property
    def rootTask(self) -> RepoTask:
        assert self._taskStack
        return self._taskStack[0]

    @property
    def isRootTask(self) -> bool:
        return self.rootTask is self


    def parentWidget(self) -> QWidget:
        p = self.parent()
        while p:
            if isinstance(p, QWidget):
                return p
            p = p.parent()
        raise ValueError(F"RepoTask {self} has no parent widget")

    @property
    def rw(self) -> 'RepoWidget':  # hack for now - assume parent is a RepoWidget
        pw = self.parentWidget()
        if DEVDEBUG:
            from gitfourchette.repowidget import RepoWidget
            assert isinstance(pw, RepoWidget)
        return pw

    def setRepo(self, repo: Repo):
        self.repo = repo

    def __str__(self):
        return self.objectName()

    def canKill(self, task: RepoTask):
        """
        Return true if this task is allowed to take precedence over the given running task.
        """
        return False

    def flow(self, *args, **kwargs) -> FlowGeneratorType:
        """
        Generator that performs the task. You can think of this as a coroutine.

        You can control the flow of the coroutine by yielding a `FlowControlToken` object.
        This lets you wait for you user input via dialog boxes, abort the task, or move long
        computations to a separate thread.

        It is recommended to `yield from` one of the `flowXXX` methods instead of instantiating
        a FlowControlToken directly. For example::

            meaning = QInputDialog.getInt(self.parentWidget(), "Hello",
                                          "What's the meaning of life?")
            yield from self.flowEnterWorkerThread()
            expensiveComputationCorrect = meaning == 42
            yield from self.flowEnterUiThread()
            if not expensiveComputationCorrect:
                raise AbortTask("Sorry, computer says no.")

        The coroutine always starts on the UI thread.
        """
        pass

    def cleanup(self):
        """
        Clean up any resources used by the task on completion or failure.
        Meant to be overridden by your task.
        Called from UI thread.
        """
        assert onAppThread()

    def onError(self, exc: Exception):
        """
        Report an error to the user if flow() was interrupted by an exception.
        Can be overridden by your task, but you should call super().onError() if you can't handle the exception.
        Called from the UI thread, after cleanup().
        """
        if isinstance(exc, ConflictError):
            showConflictErrorMessage(self.parentWidget(), exc, self.name())
        elif isinstance(exc, MultiFileError):
            # Patch doesn't apply
            message = tr("Operation failed: {0}.").format(escape(self.name()))
            for filePath, fileException in exc.file_exceptions.items():
                message += "<br><br><b>" + escape(filePath) + "</b><br>" + escape(str(fileException))
            showWarning(self.parentWidget(), self.name(), message)
        else:
            message = tr("Operation failed: {0}.").format(escape(self.name()))
            excMessageBox(exc, title=self.name(), message=message, parent=self.parentWidget())

    def prereqs(self) -> TaskPrereqs:
        return TaskPrereqs.Nothing

    def effects(self) -> TaskEffects:
        """
        Returns which parts of the UI should be refreshed when this task is done.
        """
        return TaskEffects.Nothing

    def flowEnterWorkerThread(self):
        """
        Moves the task to a non-UI thread.
        (Note that the flow always starts on the UI thread.)

        This function is intended to be called by flow() with "yield from".
        """
        yield FlowControlToken(FlowControlToken.Kind.CONTINUE_ON_WORK_THREAD)

    def flowEnterUiThread(self):
        """
        Returns the task to the UI thread.
        (Note that the flow always starts on the UI thread.)

        This function is intended to be called by flow() with "yield from".
        """
        yield FlowControlToken(FlowControlToken.Kind.CONTINUE_ON_UI_THREAD)

    def flowSubtask(self, subtaskClass: Type[RepoTask], *args, **kwargs
                    ) -> Generator[FlowControlToken, None, RepoTask]:
        """
        Runs a subtask's flow() method as if it were part of this task.
        Note that if the subtask raises an exception, the root task's flow will be stopped as well.
        You must be on the UI thread before starting a subtask.

        This function is intended to be called by flow() with "yield from".
        """

        assert onAppThread(), "Subtask must be started start on UI thread"

        # To ensure correct deletion of the subtask when we get deleted, we are the subtask's parent
        subtask = subtaskClass(self)
        subtask.setRepo(self.repo)
        subtask.setObjectName(f"{self.objectName()}:sub{subtask.objectName()}")
        logger.debug(f"{self}: Entering subtask {subtask}")

        # Push subtask onto stack
        subtask._taskStack = self._taskStack  # share reference to task stack
        self._taskStack.append(subtask)

        # Actually perform the subtask
        yield from subtask.flow(*args, **kwargs)

        # Make sure we're back on the UI thread before re-entering the root task
        if not onAppThread():
            yield FlowControlToken(FlowControlToken.Kind.CONTINUE_ON_UI_THREAD)

        # Clean up subtask (on UI thread)
        subtask.cleanup()

        # Pop subtask off stack
        assert self._taskStack[-1] is subtask
        self._taskStack.pop()

        return subtask

    def flowDialog(self, dialog: QDialog, abortTaskIfRejected=True):
        """
        Re-enters the flow when the QDialog is accepted or rejected.
        If abortTaskIfRejected is True, the task is aborted if the dialog was rejected.

        This function is intended to be called by flow() with "yield from".
        """

        assert onAppThread()  # we'll touch the UI

        waitToken = FlowControlToken(FlowControlToken.Kind.WAIT_READY)
        didReject = False

        def onReject():
            nonlocal didReject
            didReject = True

        dialog.rejected.connect(onReject)
        dialog.rejected.connect(waitToken.ready)
        dialog.accepted.connect(waitToken.ready)

        dialog.show()

        yield waitToken

        if abortTaskIfRejected and didReject:
            dialog.deleteLater()
            raise AbortTask("")

    def flowConfirm(
            self,
            title: str = "",
            text: str = "",
            buttonIcon: (QStyle.StandardPixmap | str | None) = None,
            verb: str = "",
            cancelText: str = "",
            detailText: str = "",
            detailLink: str = "",
    ):
        """
        Asks the user to confirm the operation via a message box.
        Interrupts flow() if the user denies.

        This function is intended to be called by flow() with "yield from".
        """

        assert onAppThread()  # we'll touch the UI

        if not title:
            title = self.name()

        if not verb:
            verb = title

        qmb = asyncMessageBox(self.parentWidget(), 'question', title, text,
                              QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)

        # Using QMessageBox.StandardButton.Ok instead of QMessageBox.StandardButton.Discard
        # so it connects to the "accepted" signal.
        yes: QAbstractButton = qmb.button(QMessageBox.StandardButton.Ok)
        if buttonIcon:
            yes.setIcon(stockIcon(buttonIcon))
        yes.setText(verb)

        if cancelText:
            qmb.button(QMessageBox.StandardButton.Cancel).setText(cancelText)

        if detailText:
            if not detailLink:
                qmb.setInformativeText(detailText)
            else:
                qmb.setInformativeText("<a href='_'>{0}</a>".format(detailLink))

                infoLabel: QLabel = qmb.findChild(QLabel, "qt_msgbox_informativelabel")
                if infoLabel:
                    infoLabel.setOpenExternalLinks(False)
                    infoLabel.setToolTip(detailText)
                    infoLabel.linkActivated.connect(lambda: QToolTip.showText(QCursor.pos(), detailText, infoLabel))

        qmb.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        yield from self.flowDialog(qmb)

    def checkPrereqs(self):
        prereqs = self.prereqs()
        repo = self.repo

        if TaskPrereqs.NoConflicts in prereqs and repo.any_conflicts:
            raise AbortTask(self.tr("Fix merge conflicts before performing this action."))

        if TaskPrereqs.NoUnborn in prereqs and repo.head_is_unborn:
            raise AbortTask(paragraphs(
                self.tr("There are no commits in this repository yet."),
                self.tr("Create the initial commit in this repository before performing this action.")))

        if TaskPrereqs.NoCherrypick in prereqs and repo.state() == RepositoryState.CHERRYPICK:
            raise AbortTask(paragraphs(
                self.tr("You are in the middle of a cherry-pick."),
                self.tr("Before performing this action, conclude the cherry-pick.")))

        if TaskPrereqs.NoStagedChanges in prereqs and repo.any_staged_changes:
            raise AbortTask(paragraphs(
                self.tr("You have staged changes."),
                self.tr("Before performing this action, commit your changes or stash them.")))


class RepoTaskRunner(QObject):
    refreshPostTask = Signal(RepoTask)
    progress = Signal(str, bool)
    repoGone = Signal()

    _continueFlow = Signal(object)
    "Connected to _iterateFlow"

    _threadPool: QThreadPool

    _currentTask: RepoTask | None
    "Task that is currently running"

    _zombieTask: RepoTask | None
    "Task that is being interrupted"

    _currentTaskBenchmark = Benchmark | None
    "Context manager"

    def __init__(self, parent: QObject):
        super().__init__(parent)
        self.setObjectName("RepoTaskRunner")
        self._currentTask = None
        self._zombieTask = None
        self._currentTaskBenchmark = None

        from gitfourchette import settings
        self.forceSerial = bool(settings.SYNC_TASKS)

        self._threadPool = QThreadPool(parent)
        self._threadPool.setMaxThreadCount(1)

    @property
    def currentTask(self):
        return self._currentTask

    def isBusy(self):
        return self._currentTask is not None or self._zombieTask is not None or self._threadPool.activeThreadCount() > 0

    def killCurrentTask(self):
        """
        Interrupt current task next time it yields a FlowControlToken.

        The task will not die immediately; use joinZombieTask() after killing
        the task to block the current thread until the task runner is empty.
        """
        if not self._currentTask:
            # Nothing to kill.
            return

        if not self._zombieTask:
            # Move the currently-running task to zombie mode.
            # It'll get deleted next time it yields a FlowControlToken.
            self._zombieTask = self._currentTask
        else:
            # There's already a zombie. This means that the current task hasn't
            # started yet - it's waiting on the zombie to die.
            # Just overwrite the current task, but let the zombie die cleanly.
            assert self._currentTask._currentIteration == 0, "_currentTask isn't supposed to have started yet!"
            self._currentTask.deleteLater()

        self._currentTask = None

    def joinZombieTask(self):
        """Block UI thread until the current zombie task is dead.
        Returns immediately if there's no zombie task."""

        assert onAppThread()
        while self._zombieTask:
            QThread.yieldCurrentThread()
            QThread.msleep(30)
            flags = QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents
            flags |= QEventLoop.ProcessEventsFlag.WaitForMoreEvents
            QApplication.processEvents(flags, 30)
        assert not self.isBusy()

    def put(self, task: RepoTask, *args, **kwargs):
        assert onAppThread()

        # Get flow generator
        task._currentFlow = task.flow(*args, **kwargs)
        assert isinstance(task._currentFlow, Generator), "flow() must contain at least one yield statement"

        if not self._currentTask:
            self._currentTask = task
            self._startTask(task)

        elif task.canKill(self._currentTask):
            logger.info(f"Task {task} killed task {self._currentTask}")
            self.killCurrentTask()
            self._currentTask = task

        else:
            message = self.tr("Please wait for the current operation to complete ({0})."
                              ).format(hquo(self._currentTask.name()))
            showInformation(task.parentWidget(), self.tr("Operation in progress"), "<html>" + message)

    def _startTask(self, task: RepoTask):
        assert self._currentTask == task
        assert task._currentFlow

        logger.debug(f"Start task {task}")

        self._currentTaskBenchmark = Benchmark(str(task))
        self._currentTaskBenchmark.__enter__()

        # Prepare internal signal for coroutine continuation
        self._continueFlow.connect(lambda result: self._iterateFlow(task, result))

        # Check task prerequisites
        try:
            task.checkPrereqs()
        except AbortTask as abort:
            self.reportAbortTask(task, abort)
            self._releaseTask(task)
            return

        # Prime the flow (i.e. start coroutine)
        self._iterateFlow(task, FlowControlToken())

    def _iterateFlow(self, task: RepoTask, nextResult: FlowControlToken | BaseException):
        while nextResult:
            result = nextResult
            nextResult = None

            flow = task._currentFlow
            task._currentIteration += 1

            assert onAppThread()

            assert not isinstance(result, Generator), \
                "You're trying to yield a nested generator. Did you mean 'yield from'?"

            # Wrap up zombie task (task that was interrupted earlier)
            if task is self._zombieTask:
                assert task is not self._currentTask
                self._releaseTask(task)
                task.deleteLater()

                # Another task is queued up, start it now
                if self._currentTask:
                    self._startTask(self._currentTask)
                return

            assert task is self._currentTask

            if isinstance(result, FlowControlToken):
                control = result.flowControl

                if control == FlowControlToken.Kind.WAIT_READY:
                    self.progress.emit("", False)

                    # Re-enter when user is ready
                    result.ready.connect(lambda: self._iterateFlow(task, FlowControlToken()))

                elif not self.forceSerial and control == FlowControlToken.Kind.CONTINUE_ON_WORK_THREAD:
                    busyMessage = self.tr("Busy: {0}...").format(task.name())
                    self.progress.emit(busyMessage, True)

                    # Wrapper around `next(flow)`.
                    # It will, in turn, emit _continueFlow, which will re-enter _iterateFlow.
                    wrapper = QRunnable.create(lambda: self._emitNextToken(flow))
                    self._threadPool.start(wrapper)

                else:
                    # Get next continuation token on this thread then loop to beginning of _iterateFlow
                    nextResult = self._getNextToken(flow)

            elif isinstance(result, BaseException):
                exception: BaseException = result

                # Stop tracking this task
                self._releaseTask(task)

                if isinstance(exception, StopIteration):
                    # No more steps in the flow
                    logger.debug(f"Task successful: {task}")
                    self.refreshPostTask.emit(task)
                elif isinstance(exception, AbortTask):
                    # Controlled exit, show message (if any)
                    self.reportAbortTask(task, exception)
                elif isinstance(exception, RepoGoneError):
                    self.repoGone.emit()
                else:
                    # Run task's error callback
                    task.onError(exception)

                task.deleteLater()

            else:
                assert False, ("In a RepoTask coroutine, you can only yield a FlowControlToken "
                               f"(you yielded: {type(result).__name__})")

    @staticmethod
    def _getNextToken(flow: RepoTask.FlowGeneratorType):
        try:
            return next(flow)
        except BaseException as exception:
            return exception

    def _emitNextToken(self, flow: RepoTask.FlowGeneratorType):
        nextToken = self._getNextToken(flow)
        self._continueFlow.emit(nextToken)
        return nextToken

    def _releaseTask(self, task: RepoTask):
        logger.debug(f"End task {task}")
        self.progress.emit("", False)
        self._currentTaskBenchmark.__exit__(None, None, None)

        assert onAppThread()
        assert task is self._currentTask or task is self._zombieTask
        assert task.isRootTask

        # Clean up all tasks in the stack (remember, we're the root stack)
        assert task in task._taskStack
        while task._taskStack:
            subtask = task._taskStack.pop()
            subtask.cleanup()

        self._continueFlow.disconnect()

        task._currentFlow = None

        if task is self._currentTask:
            self._currentTask = None
        elif task is self._zombieTask:
            self._zombieTask = None
        else:
            assert False

    def reportAbortTask(self, task: RepoTask, exception: AbortTask):
        message = str(exception)
        if message and exception.asStatusMessage:
            self.progress.emit("\u26a0 " + message, False)
        elif message:
            qmb = asyncMessageBox(self.parent(), exception.icon, task.name(), message)
            qmb.show()


class TaskInvoker(QObject):
    """Singleton that lets you dispatch tasks from anywhere in the application."""

    invokeSignal = Signal(object, tuple)
    _instance: TaskInvoker | None = None

    @staticmethod
    def instance():
        if TaskInvoker._instance is None:
            TaskInvoker._instance = TaskInvoker(None)
            TaskInvoker._instance.setObjectName("RepoTaskInvoker")
        return TaskInvoker._instance

    @staticmethod
    def invoke(taskType: Type[RepoTask], *taskArgs):
        TaskInvoker.instance().invokeSignal.emit(taskType, taskArgs)


