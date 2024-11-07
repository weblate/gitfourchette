# -----------------------------------------------------------------------------
# Copyright (C) 2024 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

from __future__ import annotations

import enum
import logging
import warnings
from collections.abc import Generator
from typing import Any, TYPE_CHECKING

from gitfourchette.nav import NavLocator
from gitfourchette.porcelain import ConflictError, MultiFileError, RepositoryState
from gitfourchette.qt import *
from gitfourchette.repomodel import RepoModel
from gitfourchette.settings import DEVDEBUG
from gitfourchette.toolbox import *

if TYPE_CHECKING:
    from gitfourchette.repowidget import RepoWidget

logger = logging.getLogger(__name__)


def showConflictErrorMessage(parent: QWidget, exc: ConflictError, opName="Operation"):
    numConflicts = len(exc.conflicts)

    # lupdate doesn't pick up the plural form with translate("Context", "%n", "", numConflicts)
    title = tr("%n conflicting files", "", numConflicts)
    nFilesSubmessage = tr("%n files", "", numConflicts)
    nFilesSubmessage = f"<b>{nFilesSubmessage}</b>"

    if exc.description == "workdir":
        message = translate("Conflict", "Operation {0} conflicts with {1} in the working directory:"
                            ).format(bquo(opName), nFilesSubmessage)
    elif exc.description == "HEAD":
        message = translate("Conflict", "Operation {0} conflicts with {1} in the commit at HEAD:"
                            ).format(bquo(opName), nFilesSubmessage)
    else:
        message = translate("Conflict", "Operation {0} has caused a conflict with {1} ({2}):"
                            ).format(bquo(opName), nFilesSubmessage, exc.description)

    qmb = showWarning(parent, title, message)
    addULToMessageBox(qmb, exc.conflicts)

    if exc.description == "workdir":
        dt = qmb.detailedText()
        dt += translate("Conflict", "Before you try again, you should either "
                                    "commit, stash, or discard your changes.")
        qmb.setDetailedText(dt)


class TaskPrereqs(enum.IntFlag):
    Nothing = 0
    NoUnborn = enum.auto()
    NoDetached = enum.auto()
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

    Index = enum.auto()
    "Reload the index."

    DefaultRefresh = Workdir | Refs | Remotes | Index
    "Default flags for RepoWidget.refreshRepo()"
    # Index is included so the banner can warn about conflicts
    # regardless of what part of the repo is being viewed.


class FlowControlToken(QObject):
    """
    Object that can be yielded from `RepoTask.flow()` to control the flow of the coroutine.
    """

    class Kind(enum.IntEnum):
        ContinueOnUiThread = enum.auto()
        ContinueOnWorkThread = enum.auto()
        WaitReady = enum.auto()

    ready = Signal()
    flowControl: Kind

    def __init__(self, flowControl: Kind = Kind.ContinueOnUiThread):
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

    repoModel: RepoModel | None

    jumpTo: NavLocator
    """ Jump to this location when this task completes. """

    effects: TaskEffects.Nothing
    """ Which parts of the UI should be refreshed when this task completes. """

    _postStatus: str
    """ Display this message in the status bar after completion (user code should use the getter/setter). """

    _postStatusLocked: bool
    """ Subtasks can override postStatus as long as this flag is unset.
    This flag is set when user code sets postStatus manually (via the setter). """

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
    def invoke(cls, invoker: QObject, *args, **kwargs):
        TaskInvoker.invoke(invoker, cls, *args, **kwargs)

    def __init__(self, parent: QObject):
        super().__init__(parent)
        self.repo = None
        self.repoModel = None
        self._currentFlow = None
        self._currentIteration = 0
        self.setObjectName(self.__class__.__name__)
        self.jumpTo = NavLocator()
        self.effects = TaskEffects.Nothing
        self._postStatus = ""
        self._postStatusLocked = False
        self._taskStack = [self]
        self._runningOnUiThread = True  # for debugging

    @property
    def rootTask(self) -> RepoTask:
        assert self._taskStack
        return self._taskStack[0]

    @property
    def isRootTask(self) -> bool:
        return self.rootTask is self

    def parentWidget(self) -> QWidget:
        return findParentWidget(self)

    @property
    def rw(self) -> RepoWidget:  # hack for now - assume parent is a RepoWidget
        pw = self.parentWidget()
        if DEVDEBUG:
            from gitfourchette.repowidget import RepoWidget
            assert isinstance(pw, RepoWidget)
        return pw

    def setRepoModel(self, repoModel: RepoModel):
        self.repoModel = repoModel
        if self.repoModel:
            self.repo = repoModel.repo

    def __str__(self):
        return self.objectName()

    def canKill(self, task: RepoTask) -> bool:
        """
        Return true if this task is allowed to take precedence over the given running task.
        """
        return False

    def _isRunningOnAppThread(self):
        return onAppThread() and self._runningOnUiThread

    @classmethod
    def makeInternalLink(cls, **kwargs):
        return makeInternalLink("exec", urlPath=cls.__name__, urlFragment="", **kwargs)

    def isCritical(self) -> bool:
        """
        Return true if this task must be queued up to be run at a later date
        if the TaskRunner isn't available immediately.

        This is useful if the task is invoked to respond to an external event,
        (e.g. the task fires when an external program quits),
        and you don't want this task to be silently dropped.
        """
        return False

    @property
    def postStatus(self):
        """ Display this message in the status bar after completion. """
        return self._postStatus

    @postStatus.setter
    def postStatus(self, value):
        self._postStatus = value
        self._postStatusLocked = True

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
            details = []
            if exc.message:
                message = exc.message
            else:
                message = tr("Operation failed: {0}.").format(escape(self.name()))
            for filePath, fileException in exc.file_exceptions.items():
                if fileException:
                    details.append(f"<b>{escape(filePath)}</b>: {escape(str(fileException))}")
                else:
                    details.append(escape(filePath))
            qmb = asyncMessageBox(self.parentWidget(), 'warning', self.name(), message)
            addULToMessageBox(qmb, details)
            qmb.show()
        else:
            message = tr("Operation failed: {0}.").format(escape(self.name()))
            excMessageBox(exc, title=self.name(), message=message, parent=self.parentWidget())

    def prereqs(self) -> TaskPrereqs:
        return TaskPrereqs.Nothing

    def flowEnterWorkerThread(self):
        """
        Move the task to a non-UI thread.
        (Note that the flow always starts on the UI thread.)

        This function is intended to be called by flow() with "yield from".
        """
        assert self._currentFlow is not None
        self._runningOnUiThread = False
        yield FlowControlToken(FlowControlToken.Kind.ContinueOnWorkThread)

    def flowEnterUiThread(self):
        """
        Move the task to the UI thread.
        (Note that the flow always starts on the UI thread.)

        This function is intended to be called by flow() with "yield from".
        """
        assert self._currentFlow is not None
        self._runningOnUiThread = True
        yield FlowControlToken(FlowControlToken.Kind.ContinueOnUiThread)

    def flowSubtask(self, subtaskClass: type[RepoTask], *args, **kwargs
                    ) -> Generator[FlowControlToken, None, RepoTask]:
        """
        Run a subtask's flow() method as if it were part of this task.
        Note that if the subtask raises an exception, the root task's flow will be stopped as well.
        You must be on the UI thread before starting a subtask.

        This function is intended to be called by flow() with "yield from".
        """

        assert self._currentFlow is not None
        assert self._isRunningOnAppThread(), "Subtask must be started start on UI thread"

        # To ensure correct deletion of the subtask when we get deleted, we are the subtask's parent
        subtask = subtaskClass(self)
        subtask.setRepoModel(self.repoModel)
        subtask.setObjectName(f"{self.objectName()}:{subtask.objectName()}")
        # logger.debug(f"Subtask {subtask}")

        # Push subtask onto stack
        subtask._taskStack = self._taskStack  # share reference to task stack
        self._taskStack.append(subtask)

        # Get flow generator from subtask
        subtask._currentFlow = subtask.flow(*args, **kwargs)
        assert isinstance(subtask._currentFlow, Generator), "flow() must contain at least one yield statement"

        # Actually perform the subtask
        yield from subtask._currentFlow

        # Make sure we're back on the UI thread before re-entering the root task
        if not self._isRunningOnAppThread():
            yield FlowControlToken(FlowControlToken.Kind.ContinueOnUiThread)

        # Pop subtask off stack
        rc = self._popSubtask()
        assert rc is subtask

        return subtask

    def _popSubtask(self) -> RepoTask:
        assert self._taskStack, "task stack is already empty!"
        assert onAppThread()

        # Pop last subtask off stack
        subtask = self._taskStack.pop()

        # Percolate effect bits to caller task
        self.effects |= subtask.effects

        # Percolate postStatus to caller task if it's not manually overridden
        if not self._postStatusLocked and subtask.postStatus:
            self._postStatus = subtask.postStatus

        # Percolate jumpTo to caller task
        if not self.jumpTo:
            self.jumpTo = subtask.jumpTo
        elif subtask.jumpTo and subtask.jumpTo != self.jumpTo:
            warnings.warn(f"Subtask {subtask}: Ignoring subtask jumpTo")

        # Clean up subtask (on UI thread)
        subtask.cleanup()

        return subtask

    def flowRequestForegroundUi(self):
        """
        Pause the coroutine until the RepoWidget is the foreground tab.

        This function is intended to be called by flow() with "yield from".
        """
        assert self._currentFlow is not None
        assert self._isRunningOnAppThread()

        if not self.parentWidget().isVisible():
            token = FlowControlToken(FlowControlToken.Kind.WaitReady)
            self.parentWidget().becameVisible.connect(token.ready)
            yield token

    def flowDialog(self, dialog: QDialog, abortTaskIfRejected=True, proceedSignal=None):
        """
        Show a QDialog, then pause the coroutine until it's accepted or rejected.

        If abortTaskIfRejected is True, rejecting the dialog causes the task
        to be aborted altogether.

        This function is intended to be called by flow() with "yield from".
        """

        assert self._currentFlow is not None
        assert self._isRunningOnAppThread()  # we'll touch the UI

        yield from self.flowRequestForegroundUi()

        waitToken = FlowControlToken(FlowControlToken.Kind.WaitReady)
        didReject = False
        proceedSignal = proceedSignal or dialog.accepted

        def onReject():
            nonlocal didReject
            didReject = True

        dialog.rejected.connect(onReject)
        dialog.rejected.connect(waitToken.ready)
        proceedSignal.connect(waitToken.ready)

        dialog.show()

        yield waitToken

        dialog.rejected.disconnect(onReject)
        dialog.rejected.disconnect(waitToken.ready)
        proceedSignal.disconnect(waitToken.ready)

        if abortTaskIfRejected and didReject:
            dialog.deleteLater()
            raise AbortTask("")

    def flowConfirm(
            self,
            title: str = "",
            text: str = "",
            buttonIcon: str = "",
            verb: str = "",
            cancelText: str = "",
            informativeText: str = "",
            informativeLink: str = "",
            detailText: str = "",
            detailList: list[str] | None = None,
            dontShowAgainKey: str = "",
            canCancel: bool = True,
            icon: MessageBoxIconName = "",
            checkbox: QCheckBox | None = None,
    ):
        """
        Ask the user to confirm the operation via a message box.
        Interrupts flow() if the user denies.

        This function is intended to be called by flow() with "yield from".
        """

        assert self._currentFlow is not None
        assert self._isRunningOnAppThread()  # we'll touch the UI

        if dontShowAgainKey:
            from gitfourchette import settings
            if dontShowAgainKey in settings.prefs.dontShowAgain:
                logger.debug(f"Skipping dontShowAgainMessage: {text}")
                return

        if not title:
            title = self.name()

        if not verb and canCancel:
            verb = title

        buttonMask = QMessageBox.StandardButton.Ok
        if canCancel:
            icon = icon or "question"
            buttonMask |= QMessageBox.StandardButton.Cancel
        else:
            icon = icon or "information"

        qmb = asyncMessageBox(self.parentWidget(), icon, title, text, buttonMask)

        dontShowAgainCheckBox = None
        if dontShowAgainKey:
            assert not checkbox
            dontShowAgainPrompt = tr("Don’t ask me to confirm this again") if canCancel else tr("Don’t show this again")
            dontShowAgainCheckBox = QCheckBox(dontShowAgainPrompt, qmb)
            tweakWidgetFont(dontShowAgainCheckBox, 80)
            qmb.setCheckBox(dontShowAgainCheckBox)
        elif checkbox:
            qmb.setCheckBox(checkbox)

        # Using QMessageBox.StandardButton.Ok instead of QMessageBox.StandardButton.Discard
        # so it connects to the "accepted" signal.
        yes: QAbstractButton = qmb.button(QMessageBox.StandardButton.Ok)
        if buttonIcon:
            yes.setIcon(stockIcon(buttonIcon))
        if verb:
            yes.setText(verb)

        if cancelText:
            assert canCancel, "don't set cancelText when canCancel is False!"
            qmb.button(QMessageBox.StandardButton.Cancel).setText(cancelText)

        if not informativeText:
            pass
        elif not informativeLink:
            qmb.setInformativeText(informativeText)
        else:
            qmb.setInformativeText(f"<a href='_'>{informativeLink}</a>")

            infoLabel: QLabel = qmb.findChild(QLabel, "qt_msgbox_informativelabel")
            if infoLabel:
                infoLabel.setOpenExternalLinks(False)
                infoLabel.setToolTip(informativeText)
                infoLabel.linkActivated.connect(lambda: QToolTip.showText(QCursor.pos(), informativeText, infoLabel))

        if detailText:
            qmb.setDetailedText(detailText)

        if detailList:
            addULToMessageBox(qmb, detailList)

        qmb.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        yield from self.flowDialog(qmb)

        if dontShowAgainKey and dontShowAgainCheckBox.isChecked():
            from gitfourchette import settings
            settings.prefs.dontShowAgain.append(dontShowAgainKey)
            settings.prefs.setDirty()

    def checkPrereqs(self, prereqs=TaskPrereqs.Nothing):
        if prereqs == TaskPrereqs.Nothing:
            prereqs = self.prereqs()
        repo = self.repo

        if TaskPrereqs.NoConflicts in prereqs and repo.any_conflicts:
            raise AbortTask(translate("RepoTask", "Fix merge conflicts before performing this action."))

        if TaskPrereqs.NoUnborn in prereqs and repo.head_is_unborn:
            raise AbortTask(paragraphs(
                translate("RepoTask", "There are no commits in this repository yet."),
                translate("RepoTask", "Create the initial commit in this repository before performing this action.")))

        if TaskPrereqs.NoDetached in prereqs and repo.head_is_detached:
            raise AbortTask(paragraphs(
                translate("RepoTask", "You are in “detached HEAD” state."),
                translate("RepoTask", "Switch to a local branch before performing this action.")))

        if TaskPrereqs.NoCherrypick in prereqs and repo.state() == RepositoryState.CHERRYPICK:
            raise AbortTask(paragraphs(
                translate("RepoTask", "You are in the middle of a cherry-pick."),
                translate("RepoTask", "Before performing this action, conclude the cherry-pick.")))

        if TaskPrereqs.NoStagedChanges in prereqs and repo.any_staged_changes:
            raise AbortTask(paragraphs(
                translate("RepoTask", "You have staged changes."),
                translate("RepoTask", "Before performing this action, commit your changes or stash them.")))


class RepoTaskRunner(QObject):
    ForceSerial = False
    """
    Force tasks to run synchronously on the UI thread.
    Useful for debugging.
    Can be forced with command-line switch "--no-threads".
    """

    postTask = Signal(RepoTask)
    progress = Signal(str, bool)
    repoGone = Signal()
    ready = Signal()
    requestAttention = Signal()

    _continueFlow = Signal(object)
    "Connected to _iterateFlow"

    _threadPool: QThreadPool

    _currentTask: RepoTask | None
    "Task that is currently running"

    _zombieTask: RepoTask | None
    "Task that is being interrupted"

    _currentTaskBenchmark = Benchmark | None
    "Context manager"

    _criticalTaskQueue: list

    def __init__(self, parent: QObject):
        super().__init__(parent)
        self.setObjectName("RepoTaskRunner")
        self._currentTask = None
        self._zombieTask = None
        self._currentTaskBenchmark = None
        self._criticalTaskQueue = []
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
        self._threadPool.waitForDone()
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

        elif task.isCritical():
            logger.info(f"Enqueuing critical task {task}")
            self._criticalTaskQueue.append((task, args, kwargs))

        else:
            logger.info(f"Task {task} cannot kill task {self._currentTask}")
            message = self.tr("Please wait for the current operation to complete ({0})."
                              ).format(hquo(self._currentTask.name()))
            showInformation(task.parentWidget(), self.tr("Operation in progress"), "<html>" + message)

    def _startTask(self, task: RepoTask):
        assert self._currentTask == task
        assert task._currentFlow

        logger.debug(f">>> {task}")

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
        while nextResult is not None:
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

                if control == FlowControlToken.Kind.WaitReady:
                    self.progress.emit("", False)
                    self.requestAttention.emit()

                    # Re-enter when user is ready
                    result.ready.connect(lambda: self._iterateFlow(task, FlowControlToken()))

                elif not RepoTaskRunner.ForceSerial and control == FlowControlToken.Kind.ContinueOnWorkThread:
                    busyMessage = self.tr("Busy: {0}...").format(task.name())
                    self.progress.emit(busyMessage, True)

                    # Wrapper around `next(flow)`.
                    # It will, in turn, emit _continueFlow, which will re-enter _iterateFlow.
                    wrapper = QRunnable.create(lambda f=flow: self._emitNextToken(f))
                    self._threadPool.start(wrapper)

                else:
                    # Get next continuation token on this thread then loop to beginning of _iterateFlow
                    nextResult = self._getNextToken(flow)

                    assert nextResult is not None, "Do not yield None from a RepoTask coroutine"

            elif isinstance(result, BaseException):
                exception: BaseException = result

                # Flush thread pool - Wait for task background thread to wrap up cleanly,
                # otherwise we'll still appear to be busy for postTask callbacks.
                if not self._threadPool.waitForDone():
                    warnings.warn("QThreadPool failed to flush")

                # Stop tracking this task
                self._releaseTask(task)

                if isinstance(exception, StopIteration):
                    # No more steps in the flow. Task completed successfully.
                    pass
                elif isinstance(exception, AbortTask):
                    # Controlled exit, show message (if any)
                    self.reportAbortTask(task, exception)
                elif isinstance(exception, RepoGoneError):
                    # Repo directory vanished
                    self.repoGone.emit()
                else:
                    # Run task's error callback
                    task.onError(exception)

                # Emit postTask signal whether the task succeeded or not
                self.postTask.emit(task)

                task.deleteLater()

            else:
                raise NotImplementedError("In a RepoTask coroutine, you can only yield a FlowControlToken. "
                                          f"You yielded: {type(result).__name__}")

        if not self.isBusy():  # might've queued up another task...
            if self._criticalTaskQueue:
                criticalTask, args, kwargs = self._criticalTaskQueue.pop(0)
                logger.debug(f"Popping critical task {criticalTask}")
                self.put(criticalTask, *args, **kwargs)
            else:
                self.ready.emit()

    @staticmethod
    def _getNextToken(flow: RepoTask.FlowGeneratorType):
        try:
            return next(flow)
        except BaseException as exception:
            return exception

    @calledFromQThread  # enable code coverage in task threads
    def _emitNextToken(self, flow: RepoTask.FlowGeneratorType):
        nextToken = self._getNextToken(flow)
        self._continueFlow.emit(nextToken)
        return nextToken

    def _releaseTask(self, task: RepoTask):
        logger.debug(f"<<< {task}")
        self.progress.emit("", False)
        self._currentTaskBenchmark.__exit__(None, None, None)

        assert onAppThread()
        assert task is self._currentTask or task is self._zombieTask
        assert task.isRootTask

        # Clean up all tasks in the stack (remember, we're the root stack)
        assert task in task._taskStack
        while task._taskStack:
            task._popSubtask()

        self._continueFlow.disconnect()

        task._currentFlow = None

        if task is self._currentTask:
            self._currentTask = None
        elif task is self._zombieTask:
            self._zombieTask = None
        else:
            raise AssertionError("_releaseTask: task is neither current nor zombie")

    def reportAbortTask(self, task: RepoTask, exception: AbortTask):
        message = str(exception)
        if message and exception.asStatusMessage:
            self.progress.emit("\u26a0 " + message, False)
        elif message:
            qmb = asyncMessageBox(self.parent(), exception.icon, task.name(), message)
            qmb.show()


class TaskInvoker(QObject):
    """Singleton that lets you dispatch tasks from anywhere in the application."""

    invokeSignal = Signal(QObject, object, tuple, dict)
    _instance: TaskInvoker | None = None

    @staticmethod
    def instance():
        if TaskInvoker._instance is None:
            TaskInvoker._instance = TaskInvoker(None)
            TaskInvoker._instance.setObjectName("RepoTaskInvoker")
        return TaskInvoker._instance

    @staticmethod
    def invoke(invoker: QObject, taskType: type[RepoTask], *args, **kwargs):
        TaskInvoker.instance().invokeSignal.emit(invoker, taskType, args, kwargs)
