# -----------------------------------------------------------------------------
# Copyright (C) 2026 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

import dataclasses
import logging
from pathlib import Path

from gitfourchette.forms.rebasedialog import RebaseDialog
from gitfourchette.gitdriver import GitDriver
from gitfourchette.ipc.ipcprotocol import GFIpcProtocol
from gitfourchette.localization import _
from gitfourchette.nav import NavLocator, NavFlags
from gitfourchette.porcelain import Oid, RepositoryState, RebaseInfo
from gitfourchette.ipc.ipcserver import GFIpcServer
from gitfourchette.qt import *
from gitfourchette.rebase.editmsgautofillserver import EditmsgAutoFillServer
from gitfourchette.rebase.rebasemodel import parseRebaseTodo, RebasePlan
from gitfourchette.tasks import TaskPrereqs, TaskEffects
from gitfourchette.tasks.repotask import RepoTask, AbortTask
from gitfourchette.toolbox import shortHash, tquoe, paragraphs, bquo

logger = logging.getLogger(__name__)

_StandardRebaseTaskEffects = TaskEffects.Head | TaskEffects.Workdir


class InteractiveRebase(RepoTask):
    _gracefulAbortMagic = "PrepareRebaseGracefulAbort"

    def prereqs(self):
        # TODO: need clean workdir, too
        return TaskPrereqs.NoConflicts | TaskPrereqs.NoUnborn | TaskPrereqs.NoCherrypick

    def flow(self, rootCommit: Oid):
        sequenceServer = GFIpcServer(self, singleShot=True, startNow=True)
        sequenceServer.clientConnected.connect(self.onClientConnected)

        self.epilog.effects |= _StandardRebaseTaskEffects

        driver = yield from self.flowCallGit(
            "-c", "core.abbrev=no",
            "rebase", "-i", str(rootCommit),
            env={
                "GIT_SEQUENCE_EDITOR": sequenceServer.clientCommand(),
            },
            autoFail=False)

        # We expect `rebase -i` to fail with our graceful abort message.
        # If it failed for any other reason, show error message.
        if driver.exitCode() != 1 or self._gracefulAbortMagic not in driver.stderrScrollback():
            raise AbortTask(driver.htmlErrorText(), details=driver.formatCommandLine())

    def onClientConnected(self, handshake: GFIpcProtocol.Handshake, socket: QLocalSocket):
        abort = self._gracefulAbortMagic

        try:
            self.hideProcessProgress.emit(True)

            path = handshake.args[0]
            text = Path(path).read_text(encoding="utf-8")
            todo = parseRebaseTodo(text)

            info = self.repo.rebase_info(path)
            plan = RebasePlan(todo, headName=info.head_name, origHead=info.orig_head, onto=info.onto)

            dialog = RebaseDialog(self.parentWidget())
            dialog.setSequence(plan.sequence)
            dialog.accepted.connect(lambda: self.executeRebase(plan, dialog))
            dialog.show()

        except Exception as ex:
            # Switch to non-graceful abort
            abort = f"{self.__class__.__name__} failed: {ex.__class__.__name__}: {ex}"

        finally:
            # Bail from `rebase -i` until the dialog is accepted
            # Exit GIT_SEQUENCE_EDITOR with non-0 return code, causing `git rebase` to fail
            GFIpcProtocol.respondAndBail(socket, abort=abort)

    def executeRebase(self, oldPlan: RebasePlan, dialog: RebaseDialog):
        """ Run when RebaseDialog is accepted. """
        newSequence = dialog.ui.sequence.allRebaseLines()
        newPlan = dataclasses.replace(oldPlan, sequence=newSequence)
        ExecuteRebase.invoke(dialog, oldPlan, newPlan)


class ExecuteRebase(RepoTask):
    rebaseInfoAtStart: RebaseInfo | None

    def prereqs(self):
        # TODO: need clean workdir, too
        return TaskPrereqs.NoConflicts | TaskPrereqs.NoUnborn | TaskPrereqs.NoCherrypick

    def flow(self, oldPlan: RebasePlan, newPlan: RebasePlan):
        self.oldPlan = oldPlan
        self.newPlan = newPlan
        self.rebaseInfoAtStart = None
        self.failMessage = ""

        sequenceServer = GFIpcServer(self, singleShot=True, startNow=True)
        sequenceServer.clientConnected.connect(self.onClientConnected)

        self.epilog.effects |= _StandardRebaseTaskEffects
        driver = yield from self.flowCallGit(
            "-c", "core.abbrev=no",
            "rebase", "-i", str(newPlan.onto),
            env={
                "GIT_SEQUENCE_EDITOR": sequenceServer.clientCommand(),
                "GIT_EDITOR": EditmsgAutoFillServer(self).clientCommand(),
            },
            autoFail=False,
        )

        if self.failMessage:
            raise AbortTask(self.failMessage)

        assert self.rebaseInfoAtStart is not None
        _debriefRebase(self, driver, self.rebaseInfoAtStart)  # type: ignore[unreachable] # mypy is being dumb here

    def onClientConnected(self, handshake: GFIpcProtocol.Handshake, socket: QLocalSocket):
        success = False
        path = handshake.args[0]

        try:
            self.epilog.effects |= TaskEffects.Head

            text = Path(path).read_text(encoding="utf-8")
            sequence = parseRebaseTodo(text)

            info = self.repo.rebase_info(path)
            oldPlan2 = RebasePlan(sequence, headName=info.head_name, origHead=info.orig_head, onto=info.onto)
            if oldPlan2 != self.oldPlan:
                self.failMessage = paragraphs(
                    _("Cannot apply this rebase plan."),
                    _("The repository isn’t on the same branch/commit as when you started rebasing."),
                    _("The plan was made when branch {0} was checked out, and its head was at commit {1}.",
                      bquo(self.oldPlan.headName),
                      bquo(shortHash(self.oldPlan.origHead)),
                      ),
                )
                return

            # Prepare epilog message in case of success.
            # We'll override it if we're still in a rebase state after the dialog is closed.
            self.rebaseInfoAtStart = info

            # Dump new todo
            sequenceText = self.newPlan.serializeSequence()
            Path(path).write_text(sequenceText, encoding="utf-8")
            success = True
        finally:
            # Close socket, causing rebase to start executing our sequence
            abort = "" if success else "aborting rebase"
            GFIpcProtocol.respondAndBail(socket, abort=abort)


class AbortRebase(RepoTask):
    def flow(self):
        assert self.repo.state() in [
            RepositoryState.REBASE,
            RepositoryState.REBASE_INTERACTIVE,
            RepositoryState.REBASE_MERGE,
        ], f"attempting to abort non-rebase state {self.repo.state()}"

        info = self.repo.rebase_info()

        yield from self.flowConfirm(
            text=paragraphs(
                _("Do you want to abort the ongoing rebase of {0} onto {1}?",
                  tquoe(info.head_shorthand),
                  tquoe(shortHash(info.onto, maybe=True)),
                  ),

                _("Aborting will <b>clear all changes in the working directory</b>, and branch {0} will move back to {1}.",
                  tquoe(info.head_shorthand),
                  tquoe(shortHash(info.orig_head, maybe=True)),
                  ),
            ),
        )

        self.epilog.effects |= _StandardRebaseTaskEffects
        yield from self.flowCallGit("rebase", "--abort")

        self.epilog.status = _("Rebase aborted.")


class ContinueRebase(RepoTask):
    def flow(self):
        assert self.repo.state() == RepositoryState.REBASE_INTERACTIVE, \
            f"attempting to continue from state {self.repo.state()}"

        rebaseInfoAtStart = self.repo.rebase_info()

        self.epilog.effects |= _StandardRebaseTaskEffects

        # We need GIT_EDITOR to confirm the commit message:
        # - for commits marked 'reword' (fill in message from the payload we
        #   added to the todo file)
        # - after fixing conflicts (just leave message intact)
        driver = yield from self.flowCallGit(
            "rebase", "--continue",
            env={
                "GIT_EDITOR": EditmsgAutoFillServer(self).clientCommand(),
            },
            autoFail=False,
        )

        _debriefRebase(self, driver, rebaseInfoAtStart)


def _debriefRebase(task: RepoTask, driver: GitDriver, previousInfo: RebaseInfo):
    exitCode = driver.exitCode()
    unknownFailure = exitCode not in [0, 1]

    if exitCode == 1:
        stderr = driver.stderrScrollback().strip()
        if stderr.strip() == "error: nothing to do":
            # Canceled from dialog, bail quietly
            raise AbortTask()

        stdout = driver.stdoutScrollback()
        logger.debug(f"git rebase stdout: {stdout}")

        if "CONFLICT" in stdout:
            task.epilog.jumpTo = NavLocator.inUnstaged().withExtraFlags(NavFlags.SelectAnyConflict)
        else:
            unknownFailure = True

    if unknownFailure:
        # Bail loudly
        raise AbortTask(driver.htmlErrorText())

    state = task.repo.state()

    if state == RepositoryState.NONE:
        status = _("Finished rebasing {0} onto {1}.",
                   tquoe(previousInfo.head_shorthand),
                   tquoe(shortHash(previousInfo.onto, maybe=True)))
    else:
        status = _("Rebase stopped. Your input is needed to continue.")

    task.epilog.status = status
