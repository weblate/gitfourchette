from gitfourchette.qt import *
from gitfourchette import util
from gitfourchette import log
from gitfourchette import porcelain
from html import escape
import enum
import typing
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


class YieldTokens:
    class BaseToken(QObject):
        pass

    class AbortTask(BaseToken):
        pass

    class EnterAsyncSection(BaseToken):
        pass

    class ExitAsyncSection(BaseToken):
        pass

    class WaitForUser(BaseToken):
        abortTask = Signal()
        continueTask = Signal()

    class ReenterAfterDialog(WaitForUser):
        """
        Re-enters the UI flow generator when the given QDialog is finished,
        regardless of its result.
        """

        def __init__(self, dlg: QDialog):
            super().__init__(dlg)
            dlg.finished.connect(self.continueTask)


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

    def __init__(self, parent: QObject):
        super().__init__(parent)
        self.repo = None
        self.aborted = False
        self.setObjectName("RepoTask")
        self.taskID = RepoTask.globalTaskID
        RepoTask.globalTaskID += 1

    def setRepo(self, repo: pygit2.Repository):
        self.repo = repo

    def name(self):
        return str(self)

    def cancel(self):
        """
        Call this to interrupt `preExecuteUiFlow`.
        """
        self.aborted = True

    def flow(self, *args) -> typing.Generator:
        """
        Generator that performs the task.
        (In other words, this is a coroutine)

        When then generator is exhausted, execute() is called,
        unless `aborted` was set.

        Typically, you'll implement this function to ask the user for any data
        that you need to carry out the task (via dialog boxes).

        You must `yield` a subclass of `TaskYieldTokenBase` to wait for user input
        before continuing or aborting the UI flow (e.g. ReenterWhenDialogFinished,
         AbortIfDialogRejected).
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
        self.cancel()

        if warningText:
            assert util.onAppThread()
            util.showWarning(self.parent(), self.name(), warningText)

        yield YieldTokens.AbortTask(self)

    def _flowBeginWorkerThread(self):
        yield YieldTokens.EnterAsyncSection(self)

    def _flowExitWorkerThread(self):
        yield YieldTokens.ExitAsyncSection(self)

    def _flowDialog(self, dialog: QDialog, abortTaskIfRejected=True):
        yield YieldTokens.ReenterAfterDialog(dialog)

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

    currentTask: RepoTask | None
    currentTaskConnection: QMetaObject.Connection | None
    threadPool: QThreadPool

    def __init__(self, parent: QObject):
        super().__init__(parent)
        self.setObjectName("RepoTaskRunner")
        self.currentTask = None
        self.currentTaskConnection = None

        from gitfourchette import settings
        self.forceSerial = bool(settings.TEST_MODE)

        self.threadpool = QThreadPool(parent)
        self.threadpool.setMaxThreadCount(1)

    def put(self, task: RepoTask, *args):
        log.info(TAG, f"Put task {task.taskID}: {task.name()}")

        if self.currentTask is not None:
            log.warning(TAG, f"A RepoTask is already running! ({self.currentTask.taskID}, {self.currentTask.name()})")
            QMessageBox.warning(self.parent(), TAG, f"A RepoTask is already running! ({self.currentTask.taskID}, {self.currentTask.name()})")
            return

        self.currentTask = task

        # Get flow generator (i.e. start coroutine)
        flow = task.flow(*args)
        assert isinstance(flow, typing.Generator)

        # Prime the flow
        self._consumeFlow(task, flow)

    def _consumeFlow(self, task: RepoTask, flow: typing.Generator):
        assert not task.aborted, "Task aborted on flow re-entry"

        try:
            againSynchronous = True

            while againSynchronous:
                againSynchronous = False

                # TODO: ASYNC!!!
                continueToken = next(flow)

                assert not isinstance(continueToken, typing.Generator), "You're trying to yield a nested generator. Did you mean 'yield from'?"
                assert isinstance(continueToken, YieldTokens.BaseToken), "You may only yield a subclass of BaseToken"

                if isinstance(continueToken, YieldTokens.AbortTask):
                    raise StopIteration()
                elif isinstance(continueToken, YieldTokens.EnterAsyncSection):
                    # TODO: RUN ON OTHER THREAD!!!
                    againSynchronous = True
                elif isinstance(continueToken, YieldTokens.ExitAsyncSection):
                    againSynchronous = True
                elif isinstance(continueToken, YieldTokens.WaitForUser):
                    # Bind signals from the token to resume the flow when user is ready
                    continueToken.abortTask.connect(lambda: self._releaseTask(task))
                    continueToken.continueTask.connect(lambda: self._consumeFlow(task, flow))

        except StopIteration:
            # No more steps in the flow
            assert self.currentTask == task

            # Stop tracking it
            self._releaseTask(task)

            if not task.aborted:
                task.success.emit()
                self.refreshPostTask.emit(task.refreshWhat())

        except BaseException as exc:
            # An exception was thrown during the UI flow
            assert self.currentTask == task

            # Stop tracking this task
            self._releaseTask(task)

            # Run task's error callback
            task.onError(exc)

    # def _executeTask(self, task):
    #     assert task == self.currentTask
    #
    #     self.currentTaskConnection = task.finished.connect(lambda exc: self._onTaskFinished(task, exc))
    #
    #     wrapper = util.QRunnableFunctionWrapper(task.executeAndEmitSignals)
    #     if self.forceSerial:
    #         assert util.onAppThread()
    #         wrapper.run()
    #     else:
    #         self.threadpool.start(wrapper)

    # def _onTaskFinished(self, task, exc):
    #     assert task == self.currentTask
    #
    #     self._releaseTask(task)
    #
    #     if exc:
    #         task.onError(exc)
    #     task.postExecute(not exc)
    #     self.refreshPostTask.emit(task.refreshWhat())

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
