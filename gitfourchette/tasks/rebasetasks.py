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
from gitfourchette.porcelain import *
from gitfourchette.ipc.ipcserver import GFIpcServer
from gitfourchette.qt import *
from gitfourchette.rebase.editmsgautofillserver import EditmsgAutoFillServer
from gitfourchette.rebase.rebasemodel import parseRebaseTodo, RebasePlan
from gitfourchette.tasks import TaskPrereqs, TaskEffects
from gitfourchette.tasks.repotask import RepoTask, AbortTask
from gitfourchette.toolbox import *

logger = logging.getLogger(__name__)

_StandardRebaseTaskEffects = TaskEffects.Head | TaskEffects.Workdir

# Magic messages passed via git's stderr from the socket callback function to
# the RepoTask's main coroutine.
_AbortMagicOK = "InteractiveRebaseAbortMagicOK"
_AbortMagicNoop = "InteractiveRebaseAbortMagicNoop"
_AbortMagicToctou = "InteractiveRebaseAbortMagicToctou"


class InteractiveRebase(RepoTask):
    def prereqs(self):
        # TODO: need clean workdir, too
        return TaskPrereqs.NoConflicts | TaskPrereqs.NoUnborn | TaskPrereqs.NoCherrypick

    def flow(self, ontoCommit: Oid):
        headName = self.repo.head_branch_shorthand
        headCommit = self.repo.head_commit_id

        if headCommit == ontoCommit:
            message = paragraphs(_("No rebase is necessary."),
                                 _("{0} already points to {1}.")
                                 ).format(bquo(headName), bquo(shortHash(headCommit)))
            raise AbortTask(message, icon="information")

        sequenceServer = GFIpcServer(self, singleShot=True, startNow=True)
        sequenceServer.clientConnected.connect(self.onClientConnected)

        self.epilog.effects |= _StandardRebaseTaskEffects

        driver = yield from self.flowCallGit(
            "-c", "core.abbrev=no",
            "rebase", "-i", str(ontoCommit),
            env={
                "GIT_SEQUENCE_EDITOR": sequenceServer.clientCommand(),
            },
            autoFail=False)

        # Back from onClientConnected.
        # We expect `rebase -i` to fail with one of our magic strings.
        # If it failed for any other reason, show Git error message.
        stderr = driver.stderrScrollback()

        if _AbortMagicOK in stderr:
            pass
        elif _AbortMagicNoop in stderr:
            yield from self.confirmNoopRebase(headName, headCommit, ontoCommit)
        else:
            raise AbortTask(driver.htmlErrorText(), details=driver.formatCommandLine())

    def onClientConnected(self, handshake: GFIpcProtocol.Handshake, socket: QLocalSocket):
        abortPayload = _AbortMagicOK

        try:
            self.hideProcessProgress.emit(True)

            path = handshake.args[0]
            text = Path(path).read_text(encoding="utf-8")
            todo = parseRebaseTodo(text)

            if not todo:
                abortPayload = _AbortMagicNoop
                return

            info = self.repo.rebase_info(path)
            plan = RebasePlan(todo, headName=info.head_name, origHead=info.orig_head, onto=info.onto)

            dialog = RebaseDialog(self.parentWidget())
            dialog.setSequence(plan.sequence)
            dialog.accepted.connect(lambda: self.executeRebase(plan, dialog))
            dialog.show()

        except Exception as ex:
            # Switch to non-graceful abort
            abortPayload = f"{self.__class__.__name__} failed: {ex.__class__.__name__}: {ex}"

        finally:
            # Bail from `rebase -i` until the dialog is accepted
            # Exit GIT_SEQUENCE_EDITOR with non-0 return code, causing `git rebase` to fail
            GFIpcProtocol.respondAndBail(socket, abort=abortPayload)

    def executeRebase(self, oldPlan: RebasePlan, dialog: RebaseDialog):
        """ Run when RebaseDialog is accepted. """
        newSequence = dialog.ui.sequence.allRebaseLines()
        newPlan = dataclasses.replace(oldPlan, sequence=newSequence)
        ExecuteRebase.invoke(dialog, oldPlan, newPlan)

    def confirmNoopRebase(self, headName: str, headCommit: Oid, ontoCommit: Oid):
        message = paragraphs(
            _("There’s nothing to rebase. All commits from {0} are already in the other branch."),
            _("If you continue, this will amount to resetting {0} to {1}.")
        ).format(bquo(headName), bquo(shortHash(ontoCommit)))
        yield from self.flowConfirm(text=message, verb=_("Continue"))

        # Make sure the head didn't change while user was reading the message
        if self.repo.head_branch_shorthand != headName or self.repo.head_commit_id != headCommit:
            raise AbortTask(_toctouErrorText(headName, headCommit))

        driver = yield from self.flowCallGit("rebase", str(ontoCommit))
        _debriefRebase(self, driver, headName, headCommit, ontoCommit)


class ExecuteRebase(RepoTask):
    def prereqs(self):
        # TODO: need clean workdir, too
        return TaskPrereqs.NoConflicts | TaskPrereqs.NoUnborn | TaskPrereqs.NoCherrypick

    def flow(self, oldPlan: RebasePlan, newPlan: RebasePlan):
        self.oldPlan = oldPlan
        self.newPlan = newPlan

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

        _debriefRebase(self, driver, oldPlan.headShorthand, oldPlan.origHead, oldPlan.onto)

    def onClientConnected(self, handshake: GFIpcProtocol.Handshake, socket: QLocalSocket):
        path = handshake.args[0]
        abortPayload = "Aborting Rebase"

        try:
            self.epilog.effects |= TaskEffects.Head

            text = Path(path).read_text(encoding="utf-8")
            sequence = parseRebaseTodo(text)

            info = self.repo.rebase_info(path)
            oldPlan2 = RebasePlan(sequence, headName=info.head_name, origHead=info.orig_head, onto=info.onto)
            if oldPlan2 != self.oldPlan:
                abortPayload = _AbortMagicToctou
                return

            # Dump new todo
            sequenceText = self.newPlan.serializeSequence()
            Path(path).write_text(sequenceText, encoding="utf-8")
            abortPayload = ""  # success
        finally:
            # Close socket, causing rebase to start executing our sequence
            GFIpcProtocol.respondAndBail(socket, abort=abortPayload)


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

        _debriefRebase(self, driver, rebaseInfoAtStart.head_shorthand, rebaseInfoAtStart.orig_head, rebaseInfoAtStart.onto)


def _toctouErrorText(headName: str, headCommit: Oid):
    return paragraphs(
        _("Cannot apply this rebase plan."),
        _("The repository isn’t on the same branch/commit as when you started rebasing."),
        _("The plan was made when branch {0} was checked out, and its head was at commit {1}.",
          bquo(headName),
          bquo(shortHash(headCommit)),
          ),
    )


def _debriefRebase(task: RepoTask, driver: GitDriver, headName: str, headCommit: Oid, ontoCommit: Oid):
    exitCode = driver.exitCode()
    unknownFailure = exitCode not in [0, 1]

    if exitCode == 1:
        stderr = driver.stderrScrollback().strip()

        if stderr == "error: nothing to do":
            # Canceled from dialog, bail quietly
            raise AbortTask()

        if _AbortMagicToctou in stderr:
            raise AbortTask(_toctouErrorText(headName, headCommit))

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
        status = _("Finished rebasing {0} onto {1}.", tquoe(headName), tquo(shortHash(ontoCommit)))
    else:
        status = _("Rebase stopped. Your input is needed to continue.")

    task.epilog.status = status
