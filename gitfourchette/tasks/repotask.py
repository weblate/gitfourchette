from gitfourchette.qt import *
from gitfourchette import util
from gitfourchette import log
from gitfourchette import porcelain
from html import escape
import enum
import typing


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
    LOCALREFS = enum.auto()
    REMOTES = enum.auto()
    HEAD = enum.auto()


class TaskYieldTokenBase(QObject):
    abortTask = Signal()
    continueTask = Signal()


class ReenterWhenDialogFinished(TaskYieldTokenBase):
    """
    Re-enters the UI flow generator when the given QDialog is finished,
    regardless of its result.
    """

    def __init__(self, dlg: QDialog):
        super().__init__(dlg)
        dlg.finished.connect(self.continueTask)


class AbortIfDialogRejected(TaskYieldTokenBase):
    """
    Pauses the UI flow generator until the given QDialog is either accepted or rejected.
    - If the QDialog is rejected, the UI flow is aborted.
    - If the QDialog is accepted, the UI flow is re-entered.
    """

    def __init__(self, dlg: QDialog):
        super().__init__(dlg)
        dlg.accepted.connect(self.continueTask)
        dlg.rejected.connect(self.abortTask)
        dlg.rejected.connect(dlg.deleteLater)


class RepoTask(QObject):
    """
    Task that manipulates a repository.

    First, `preExecuteUiFlow` may prompt the user for additional information
    (e.g. via dialog screens) on the UI thread.

    The actual operation is then carried out on a separate thread in `execute`.

    Any cleanup then occurs in `postExecute` (whether `execute` succeeded or not),
    back on the UI thread.
    """

    success = Signal()
    "Emitted by executeAndEmitSignals() when execute() has finished running sucessfully."

    finished = Signal(object)
    """Emitted by executeAndEmitSignals() when execute() has finished running,
    (successfully or not). The sole argument is the exception that was raised during
    execute() -- this is None if the task ran to completion."""

    globalTaskID = 0

    def __init__(self, rw: 'RepoWidget'):
        super().__init__(rw)
        self.rw = rw
        self.aborted = False
        self.setObjectName("RepoTask")
        self.taskID = RepoTask.globalTaskID
        RepoTask.globalTaskID += 1

    def name(self):
        return str(self)

    @property
    def repo(self):
        return self.rw.repo

    def cancel(self):
        """
        Call this to interrupt `preExecuteUiFlow`.
        """
        self.aborted = True

    def preExecuteUiFlow(self) -> typing.Generator | None:
        """
        Generator to be executed before the meat of the task.

        When then generator is exhausted, execute() is called,
        unless `aborted` was set.

        Typically, you'll implement this function to ask the user for any data
        that you need to carry out the task (via dialog boxes).

        You must `yield` a subclass of `TaskYieldTokenBase` to wait for user input
        before continuing or aborting the UI flow (e.g. ReenterWhenDialogFinished,
         AbortIfDialogRejected).
        """
        pass

    def execute(self) -> None:
        """
        The "meat" of the task.
        Runs after preExecuteUiFlow.

        This function may be scheduled to run on a separate thread so that the
        UI stays responsive. Therefore, you may NOT interact with the UI here.

        You may throw an exception.
        """
        pass

    def executeAndEmitSignals(self):
        """
        Do not override!
        """
        try:
            # TODO: Mutex to regulate access to repo from entire program?
            self.execute()
            self.finished.emit(None)
            self.success.emit()
        except BaseException as exc:
            self.finished.emit(exc)

    def postExecute(self, success: bool):
        """
        Runs on the UI thread, after execute() exits.
        """
        pass

    def onError(self, exc):
        """
        Runs if preExecuteUiFlow() or execute() were interrupted by an error.
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

    def abortIfQuestionRejected(
            self,
            title: str = "",
            text: str = "",
            acceptButtonIcon: (QStyle.StandardPixmap | str | None) = None,
    ) -> TaskYieldTokenBase:
        """
        Asks the user to confirm the operation via a message box.
        Interrupts preExecuteUiFlow if the user denies.

        This function is only intended to be called during `preExecuteUiFlow`.
        It returns a TaskYieldTokenBase which you should `yield`. For example:

        >>> yield self.abortIfQuestionRejected("Question", "Really do this?")
        """

        if not title:
            title = self.name()

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
        yes.setText(title)

        qmb.show()

        qmb.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        return AbortIfDialogRejected(qmb)


class RepoTaskRunner(QObject):
    refreshPostTask = Signal(TaskAffectsWhat)

    currentTask: RepoTask | None
    currentTaskConnection: QMetaObject.Connection | None
    threadPool: QThreadPool

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("RepoTaskRunner")
        self.currentTask = None
        self.currentTaskConnection = None

        from gitfourchette import settings
        self.forceSerial = bool(settings.TEST_MODE)

        self.threadpool = QThreadPool(parent)
        self.threadpool.setMaxThreadCount(1)

    def put(self, task: RepoTask):
        log.info(TAG, f"Put task {task.taskID}: {task.name()}")

        if self.currentTask is not None:
            log.warning(TAG, f"A RepoTask is already running! ({self.currentTask.taskID}, {self.currentTask.name()})")
            QMessageBox.warning(self.parent(), TAG, f"A RepoTask is already running! ({self.currentTask.taskID}, {self.currentTask.name()})")
            return

        self.currentTask = task
        flow = task.preExecuteUiFlow()

        if flow is None:
            # No pre-execute UI flow, so run the task right away
            self._executeTask(task)
        else:
            # Prime the UI flow
            self._onContinueFlow(task, flow)

    def _onContinueFlow(self, task: RepoTask, flow: typing.Generator):
        assert not task.aborted, "Task aborted on UI flow re-entry"

        try:
            continueToken = next(flow)

            assert isinstance(continueToken, TaskYieldTokenBase), "You may only yield a subclass of TaskYieldTokenBase"

            # Bind signals from the token to resume the UI flow when the user is ready
            continueToken.abortTask.connect(lambda: self._releaseTask(task))
            continueToken.continueTask.connect(lambda: self._onContinueFlow(task, flow))

        except StopIteration:
            # No more steps in the pre-execute UI flow
            assert self.currentTask == task

            if task.aborted:
                # The flow function may have aborted the task, in which case stop tracking it.
                self._releaseTask(task)
            else:
                # Execute the meat of the task
                self._executeTask(task)

        except BaseException as exc:
            # An exception was thrown during the UI flow
            assert self.currentTask == task

            # Stop tracking this task
            self._releaseTask(task)

            # Run task's error callback
            task.onError(exc)

    def _executeTask(self, task):
        assert task == self.currentTask

        self.currentTaskConnection = task.finished.connect(lambda exc: self._onTaskFinished(task, exc))

        wrapper = util.QRunnableFunctionWrapper(task.executeAndEmitSignals)
        if self.forceSerial:
            assert util.onAppThread()
            wrapper.run()
        else:
            self.threadpool.start(wrapper)

    def _onTaskFinished(self, task, exc):
        assert task == self.currentTask

        self._releaseTask(task)

        if exc:
            task.onError(exc)
        task.postExecute(not exc)
        self.refreshPostTask.emit(task.refreshWhat())

    def _releaseTask(self, task):
        log.info(TAG, f"Pop task {task.taskID}: {task.name()}")

        assert util.onAppThread()
        assert task == self.currentTask

        if self.currentTaskConnection:
            if not PYSIDE2:
                assert isinstance(self.currentTaskConnection, QMetaObject.Connection)
                self.disconnect(self.currentTaskConnection)
            else:
                # When connecting to a signal, PySide2 returns a bool, not a QMetaObject.Connection.
                # Looks like it's a wontfix: https://bugreports.qt.io/browse/PYSIDE-1902
                task.finished.disconnect()
            self.currentTaskConnection = None

        self.currentTask.setParent(None)  # de-parent the task so that it can be garbage-collected
        self.currentTask = None

