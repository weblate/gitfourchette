from gitfourchette.benchmark import Benchmark
from gitfourchette.qt import *
from gitfourchette import util
from gitfourchette import log
from gitfourchette import porcelain
from html import escape
from typing import Any, Generator, Literal, Type
import enum
import pygit2


TAG = "RepoTaskRunner"


def showConflictErrorMessage(parent: QWidget, exc: porcelain.ConflictError, opName="Operation"):
    maxConflicts = 10
    numConflicts = len(exc.conflicts)

    # lupdate doesn't pick up the plural form with translate("Context", "%n", "", numConflicts)
    title = tr("%n conflicting file(s)", "", numConflicts)
    nFilesSubmessage = tr("<b>%n file(s)</b>", "", numConflicts)

    if exc.description == "workdir":
        message = translate("Conflict", "Operation <b>{0}</b> conflicts with {1} in the working directory:"
                            ).format(opName, nFilesSubmessage)
    elif exc.description == "HEAD":
        message = translate("Conflict", "Operation <b>{0}</b> conflicts with {1} in the commit at HEAD:"
                            ).format(opName, nFilesSubmessage)
    else:
        message = translate("Conflict", "Operation <b>{0}</b> has caused a conflict with {1} ({2}):"
                            ).format(opName, nFilesSubmessage, exc.description)

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

    qmb = util.showWarning(parent, title, message)

    if numConflicts > maxConflicts:
        qmb.setDetailedText("\n".join(exc.conflicts))


class TaskAffectsWhat(enum.IntFlag):
    NOTHING = 0
    INDEX = enum.auto()
    INDEXWRITE = enum.auto()
    LOCALREFS = enum.auto()
    REMOTES = enum.auto()
    HEAD = enum.auto()
    DEFAULT = INDEX | LOCALREFS | REMOTES


class FlowControlToken(QObject):
    """
    Object that can be yielded from `RepoTask.flow()` to control the flow of the coroutine.
    """

    class Kind(enum.IntEnum):
        CONTINUE_ON_UI_THREAD = enum.auto()
        CONTINUE_ON_WORK_THREAD = enum.auto()
        ABORT_TASK = enum.auto()
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


class RepoTask(QObject):
    """
    Task that manipulates a repository.
    """

    success = Signal()
    "Emitted when the task has successfully run to completion."

    _globalTaskCounter = 0

    repo: pygit2.Repository | None
    taskID: int

    _currentFlow: Generator
    _currentIteration: int

    def __init__(self, parent: QObject):
        super().__init__(parent)
        self.setObjectName("RepoTask")
        self.repo = None
        self._currentFlow = None
        self._currentIteration = 0
        self.taskID = RepoTask._globalTaskCounter
        RepoTask._globalTaskCounter += 1

    def setRepo(self, repo: pygit2.Repository):
        self.repo = repo

    def name(self):
        return str(self)

    def __str__(self):
        return f"{self.__class__.__name__}#{self.taskID}"

    def canKill(self, task: 'RepoTask'):
        return False

    def flow(self, *args, **kwargs) -> Generator:
        """
        Generator that performs the task. You can think of this as a coroutine.

        When then generator is exhausted, the `success` signal is emitted.

        You can control the flow of the coroutine by yielding a `FlowControlToken` object.
        This lets you wait for you user input via dialog boxes, abort the task, or move long
        computations to a separate thread.

        It is recommended to `yield from` one of the `_flowXXX` methods instead of instantiating
        a FlowControlToken directly. For example::

            meaning = QInputDialog.getInt(self.parent(), "Hello",
                                          "What's the meaning of life?")
            yield from self._flowBeginWorkerThread()
            expensiveComputationCorrect = meaning == 42
            yield from self._flowExitWorkerThread()
            if not expensiveComputationCorrect:
                yield from self._flowAbort("Sorry, computer says no.")
        """
        pass

    def onError(self, exc):
        """
        Runs if flow() was interrupted by an error.
        """
        if isinstance(exc, porcelain.ConflictError):
            showConflictErrorMessage(self.parent(), exc, self.name())
        elif isinstance(exc, porcelain.MultiFileError):
            # Patch doesn't apply
            message = self.tr("Operation failed: {0}.").format(escape(self.name()))
            for filePath, fileException in exc.fileExceptions.items():
                message += "<br><br><b>" + escape(filePath) + "</b><br>" + escape(str(fileException))
            util.showWarning(self.parent(), self.name(), message)
        else:
            message = self.tr("Operation failed: {0}.").format(escape(self.name()))
            util.excMessageBox(exc, title=self.name(), message=message, parent=self.parent())

    def refreshWhat(self) -> TaskAffectsWhat:
        """
        Returns which parts of the UI should be refreshed when this task is done.
        """
        return TaskAffectsWhat.NOTHING

    def _flowAbort(
            self,
            warningText: str = "",
            warningTextIcon: util.MessageBoxIconName = "warning"
    ):
        """
        Aborts the task with an optional error message.
        The success signal will NOT be emitted.
        """

        if warningText:
            assert util.onAppThread()
            qmb = util.asyncMessageBox(self.parent(), warningTextIcon, self.name(), warningText)
            qmb.show()

        yield FlowControlToken(FlowControlToken.Kind.ABORT_TASK)

    def _flowBeginWorkerThread(self):
        """
        Moves the task to a non-UI thread.
        (Note that the flow always starts on the UI thread.)
        """
        yield FlowControlToken(FlowControlToken.Kind.CONTINUE_ON_WORK_THREAD)

    def _flowExitWorkerThread(self):
        """
        Returns the task to the UI thread.
        """
        yield FlowControlToken(FlowControlToken.Kind.CONTINUE_ON_UI_THREAD)

    def _flowSubtask(self, subtaskClass: Type['RepoTask'], *args, **kwargs):
        """
        Runs a subtask's flow() method as if it were part of this task.
        Note that if the subtask raises an exception, the root task's flow will be stopped as well.
        """
        assert util.onAppThread(), "Subtask must start on UI thread"

        subtask = subtaskClass(self.parent())
        subtask.setRepo(self.repo)
        yield from subtask.flow(*args, **kwargs)

        # Make sure we're back on the UI thread before re-entering the root task
        if not util.onAppThread():
            yield FlowControlToken(FlowControlToken.Kind.CONTINUE_ON_UI_THREAD)

        return subtask

    def _flowDialog(self, dialog: QDialog, abortTaskIfRejected=True):
        """
        Re-enters the flow when the QDialog is accepted or rejected.
        If abortTaskIfRejected is True, the task is aborted if the dialog was rejected.
        """
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
            yield from self._flowAbort()

    def _flowConfirm(
            self,
            title: str = "",
            text: str = "",
            buttonIcon: (QStyle.StandardPixmap | str | None) = None,
            verb: str = "",
    ):
        """
        Asks the user to confirm the operation via a message box.
        Interrupts flow() if the user denies.
        """

        if not title:
            title = self.name()

        if not verb:
            verb = title

        qmb = util.asyncMessageBox(
            self.parent(),
            'question',
            title,
            text,
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)

        # Using QMessageBox.StandardButton.Ok instead of QMessageBox.StandardButton.Discard
        # so it connects to the "accepted" signal.
        yes: QAbstractButton = qmb.button(QMessageBox.StandardButton.Ok)
        if buttonIcon:
            yes.setIcon(util.stockIcon(buttonIcon))
        yes.setText(verb)

        qmb.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        yield from self._flowDialog(qmb)


class RepoTaskRunner(QObject):
    refreshPostTask = Signal(RepoTask)
    progress = Signal(str, bool)

    _continueFlow = Signal(object)
    "Connected to _iterateFlow"

    _threadPool: QThreadPool
    _currentTask: RepoTask | None
    _zombieTask: RepoTask | None
    _currentTaskBenchmark = Benchmark | None

    def __init__(self, parent: QObject):
        super().__init__(parent)
        self.setObjectName("RepoTaskRunner")
        self._currentTask = None
        self._zombieTask = None
        self._currentTaskBenchmark = None

        from gitfourchette import settings
        self.forceSerial = bool(settings.TEST_MODE)

        self._threadPool = QThreadPool(parent)
        self._threadPool.setMaxThreadCount(1)

        self._pendingKiller = None
        self._pendingKillerArgs = []

    def isBusy(self):
        return self._currentTask is not None or self._zombieTask is not None or self._threadPool.activeThreadCount() > 0

    def put(self, task: RepoTask, *args, **kwargs):
        assert util.onAppThread()

        # Get flow generator
        task._currentFlow = task.flow(*args, **kwargs)
        assert isinstance(task._currentFlow, Generator), "flow() must contain at least one yield statement"

        if not self._currentTask:
            self._currentTask = task
            self._startTask(task)

        elif task.canKill(self._currentTask):
            log.info(TAG, f"Task {task} killed task {self._currentTask}")
            if not self._zombieTask:
                self._zombieTask = self._currentTask
            else:
                # Current task hasn't started yet, it's still waiting on the zombie to die.
                # We can kill the current task, so just overwrite it, but leave the zombie alone.
                assert self._currentTask._currentIteration == 0, "it's not supposed to have started yet!"
                self._currentTask.deleteLater()
            self._currentTask = task

        else:
            util.showInformation(self.parent(), self.tr("Operation in progress"),
                                 self.tr("Please wait for the current operation to complete. "
                                         "({0} cannot be interrupted by {1})").format(self._currentTask, task))

    def _startTask(self, task):
        assert self._currentTask == task
        assert task._currentFlow

        log.info(TAG, f"Start task {task}")

        self._currentTaskBenchmark = Benchmark(str(task))
        self._currentTaskBenchmark.__enter__()

        # Prepare internal signal for coroutine continuation
        self._continueFlow.connect(lambda result: self._iterateFlow(task, result))

        # Prime the flow (i.e. start coroutine)
        self._iterateFlow(task, FlowControlToken())

    def _iterateFlow(self, task: RepoTask, result: FlowControlToken | BaseException):
        flow = task._currentFlow
        task._currentIteration += 1
        # log.info(TAG, f"Iterate on task {task} ({task._currentIteration}) ({result})")

        assert util.onAppThread()

        assert not isinstance(result, Generator), \
            "You're trying to yield a nested generator. Did you mean 'yield from'?"

        if task is self._zombieTask:
            assert task is not self._currentTask
            self._releaseTask(task)
            task.deleteLater()
            self._startTask(self._currentTask)
            return

        assert task is self._currentTask

        if isinstance(result, FlowControlToken):
            control = result.flowControl

            if control == FlowControlToken.Kind.ABORT_TASK:
                # Stop here
                log.info(TAG, f"Task aborted: {task}")
                self._releaseTask(task)
                task.deleteLater()

            elif control == FlowControlToken.Kind.WAIT_READY:
                self.progress.emit(self.tr("Awaiting your input to resume {0}").format(task.name()), False)

                # Re-enter when user is ready
                result.ready.connect(lambda: self._iterateFlow(task, FlowControlToken()))

            else:
                self.progress.emit(self.tr("In progress: {0}...").format(task.name()), True)

                # Wrapper around `next(flow)`.
                # It will, in turn, emit _continueFlow, which will re-enter _iterateFlow.
                wrapper = util.QRunnableFunctionWrapper(lambda: self._wrapNext(flow))

                if not self.forceSerial and control == FlowControlToken.Kind.CONTINUE_ON_WORK_THREAD:
                    self._threadPool.start(wrapper)
                else:
                    wrapper.run()

        elif isinstance(result, BaseException):
            exception: BaseException = result

            # Stop tracking this task
            self._releaseTask(task)

            if isinstance(exception, StopIteration):
                # No more steps in the flow
                log.info(TAG, f"Task successful: {task}")
                task.success.emit()
                self.refreshPostTask.emit(task)
            else:
                # Run task's error callback
                task.onError(exception)

            task.deleteLater()

        else:
            assert False, f"You are only allowed to yield a FlowControlToken (you yielded: {type(result).__name__})"

    def _wrapNext(self, flow):
        try:
            nextToken = next(flow)
            self._continueFlow.emit(nextToken)
        except BaseException as exception:
            self._continueFlow.emit(exception)

    def _releaseTask(self, task: RepoTask):
        log.info(TAG, f"End task {task}")
        self.progress.emit("", False)
        self._currentTaskBenchmark.__exit__(None, None, None)

        assert util.onAppThread()
        assert task is self._currentTask or task is self._zombieTask

        self._continueFlow.disconnect()

        if task is self._currentTask:
            self._currentTask = None
        elif task is self._zombieTask:
            self._zombieTask = None
        else:
            assert False
