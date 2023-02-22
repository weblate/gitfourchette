from gitfourchette.qt import *
from gitfourchette import util
from gitfourchette import log
from gitfourchette import porcelain
from html import escape
from typing import Any, Generator
import enum
import pygit2


TAG = "RepoTaskRunner"


def showConflictErrorMessage(parent: QWidget, exc: porcelain.ConflictError, opName="Operation"):
    maxConflicts = 10
    numConflicts = len(exc.conflicts)

    title = translate("ConflictError", "%n conflicting file(s)", "", numConflicts)

    if numConflicts > maxConflicts:
        intro = translate("ConflictError", "Showing the first {0} conflicting files out of {1} total below:") \
            .format(maxConflicts, numConflicts)
    else:
        intro = translate("ConflictError", "%n conflicting file(s):", "", numConflicts)

    if exc.description == "workdir":
        message = translate("ConflictError", "Operation <b>{0}</b> conflicts with the working directory.").format(opName)
    elif exc.description == "HEAD":
        message = translate("ConflictError", "Operation <b>{0}</b> conflicts with the commit at HEAD.").format(opName)
    else:
        message = translate("ConflictError", "Operation <b>{0}</b> caused a conflict ({1}).").format(opName, exc.description)

    message += f"<br><br>{intro}<ul><li>"
    message += "</li><li>".join(exc.conflicts[:maxConflicts])
    if numConflicts > maxConflicts:
        numHidden = numConflicts - maxConflicts
        message += "</li><li><i>"
        message += translate("ConflictError", "...and %n more (click “Show Details” to view full list)", "", numHidden)
        message += "</li>"
    message += "</li></ul>"

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

    def __init__(self, parent: QObject, flowControl: Kind = Kind.CONTINUE_ON_UI_THREAD):
        super().__init__(parent)
        self.flowControl = flowControl
        self.setObjectName("FlowControlToken")


class RepoTask(QObject):
    """
    Task that manipulates a repository.
    """

    success = Signal()
    "Emitted when the task has successfully run to completion."

    _globalTaskCounter = 0

    repo: pygit2.Repository | None
    taskID: int

    def __init__(self, parent: QObject):
        super().__init__(parent)
        self.setObjectName("RepoTask")
        self.repo = None
        self.taskID = RepoTask._globalTaskCounter
        RepoTask._globalTaskCounter += 1

    def setRepo(self, repo: pygit2.Repository):
        self.repo = repo

    def name(self):
        return str(self)

    def flow(self, *args) -> Generator:
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
        else:
            message = self.tr("Operation failed: {0}.").format(escape(self.name()))
            util.excMessageBox(exc, title=self.name(), message=message, parent=self.parent())

    def refreshWhat(self) -> TaskAffectsWhat:
        """
        Returns which parts of the UI should be refreshed when this task is done.
        """
        return TaskAffectsWhat.NOTHING

    def _flowAbort(self, warningText: str = ""):
        """
        Aborts the task.
        The success signal will NOT be emitted.
        """
        if warningText:
            assert util.onAppThread()
            util.showWarning(self.parent(), self.name(), warningText)
        yield FlowControlToken(self, FlowControlToken.Kind.ABORT_TASK)

    def _flowBeginWorkerThread(self):
        """
        Moves the task to a non-UI thread.
        (Note that the flow always starts on the UI thread.)
        """
        yield FlowControlToken(self, FlowControlToken.Kind.CONTINUE_ON_WORK_THREAD)

    def _flowExitWorkerThread(self):
        """
        Returns the task to the UI thread.
        """
        yield FlowControlToken(self, FlowControlToken.Kind.CONTINUE_ON_UI_THREAD)

    def _flowDialog(self, dialog: QDialog, abortTaskIfRejected=True):
        """
        Re-enters the flow when the QDialog is finished.
        If abortTaskIfRejected is True, the task is aborted if the dialog was rejected.
        """
        token = FlowControlToken(self, FlowControlToken.Kind.WAIT_READY)
        dialog.finished.connect(token.ready)
        yield token

        if abortTaskIfRejected and dialog.result() in [QDialog.DialogCode.Rejected, QMessageBox.StandardButton.Cancel]:
            dialog.deleteLater()
            yield from self._flowAbort()

    def _flowConfirm(
            self,
            title: str = "",
            text: str = "",
            acceptButtonIcon: (QStyle.StandardPixmap | str | None) = None,
            acceptButtonText: str = "",
    ):
        """
        Asks the user to confirm the operation via a message box.
        Interrupts flow() if the user denies.
        """

        if not title:
            title = self.name()

        if not acceptButtonText:
            acceptButtonText = title

        qmb = util.asyncMessageBox(
            self.parent(),
            'question',
            title,
            text,
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)

        # Using QMessageBox.StandardButton.Ok instead of QMessageBox.StandardButton.Discard
        # so it connects to the "accepted" signal.
        yes: QAbstractButton = qmb.button(QMessageBox.StandardButton.Ok)
        if acceptButtonIcon:
            yes.setIcon(util.stockIcon(acceptButtonIcon))
        yes.setText(acceptButtonText)

        qmb.show()

        qmb.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        yield from self._flowDialog(qmb)


class RepoTaskRunner(QObject):
    refreshPostTask = Signal(TaskAffectsWhat)
    _continueFlow = Signal(object)

    _threadPool: QThreadPool
    _currentTask: RepoTask | None

    def __init__(self, parent: QObject):
        super().__init__(parent)
        self.setObjectName("RepoTaskRunner")
        self._currentTask = None

        from gitfourchette import settings
        self.forceSerial = bool(settings.TEST_MODE)

        self._threadPool = QThreadPool(parent)
        self._threadPool.setMaxThreadCount(1)

    def put(self, task: RepoTask, *args):
        log.info(TAG, f"Put task {task.taskID}: {task.name()}")

        if self._currentTask is not None:
            log.warning(TAG, f"A RepoTask is already running! ({self._currentTask.taskID}, {self._currentTask.name()})")
            QMessageBox.warning(self.parent(), TAG, f"A RepoTask is already running! ({self._currentTask.taskID}, {self._currentTask.name()})")
            return

        self._currentTask = task

        # Prepare internal signal for coroutine continuation
        self._continueFlow.connect(lambda result: self._iterateFlow(task, flow, result))

        # Get flow generator
        flow = task.flow(*args)
        assert isinstance(flow, Generator), "flow() must contain at least one yield statement"

        # Prime the flow (i.e. start coroutine)
        self._iterateFlow(task, flow, FlowControlToken(self))

    def _iterateFlow(self, task: RepoTask, flow: Generator, result: FlowControlToken | BaseException):
        assert util.onAppThread()
        assert self._currentTask == task

        assert not isinstance(result, Generator), \
            "You're trying to yield a nested generator. Did you mean 'yield from'?"

        if isinstance(result, FlowControlToken):
            control = result.flowControl

            if control == FlowControlToken.Kind.ABORT_TASK:
                # Stop here
                self._releaseTask(task)
                result.deleteLater()

            elif control == FlowControlToken.Kind.WAIT_READY:
                # Re-enter when user is ready
                result.ready.connect(lambda: self._iterateFlow(task, flow, FlowControlToken(self)))

            else:
                # Wrapper around `next(flow)`.
                # It will, in turn, emit _continueFlow, which will re-enter _iterateFlow.
                wrapper = util.QRunnableFunctionWrapper(lambda: self._wrapNext(flow))

                if not self.forceSerial and control == FlowControlToken.Kind.CONTINUE_ON_WORK_THREAD:
                    self._threadPool.start(wrapper)
                else:
                    wrapper.run()

                result.deleteLater()

        elif isinstance(result, BaseException):
            exception: BaseException = result

            # Stop tracking this task
            self._releaseTask(task)

            if isinstance(exception, StopIteration):
                # No more steps in the flow
                task.success.emit()
                self.refreshPostTask.emit(task.refreshWhat())
            else:
                # Run task's error callback
                task.onError(exception)

        else:
            assert False, f"You are only allowed to yield a FlowControlToken (you yielded: {type(result).__name__})"

    def _wrapNext(self, flow):
        try:
            nextToken = next(flow)
            self._continueFlow.emit(nextToken)
        except BaseException as exception:
            self._continueFlow.emit(exception)

    def _releaseTask(self, task: RepoTask):
        log.info(TAG, f"Pop task {task.taskID}: {task.name()}")

        assert util.onAppThread()
        assert task == self._currentTask

        self._continueFlow.disconnect()

        self._currentTask.setParent(None)  # de-parent the task so that it can be garbage-collected
        self._currentTask = None

