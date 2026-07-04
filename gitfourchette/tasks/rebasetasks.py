# -----------------------------------------------------------------------------
# Copyright (C) 2026 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

import logging
from pathlib import Path

from gitfourchette.forms.rebasedialog import RebaseDialog
from gitfourchette.ipc.ipcprotocol import GFIpcProtocol
from gitfourchette.localization import _
from gitfourchette.porcelain import Oid, RepositoryState, Repo, RebaseInfo
from gitfourchette.ipc.ipcserver import GFIpcServer
from gitfourchette.qt import *
from gitfourchette.rebase.rebasemodel import parseRebaseTodo
from gitfourchette.tasks import TaskPrereqs, TaskEffects
from gitfourchette.tasks.repotask import RepoTask
from gitfourchette.toolbox import shortHash, tquoe, paragraphs

logger = logging.getLogger(__name__)


def _rebaseEpilogStatus(repo: Repo, previousInfo: RebaseInfo) -> str:
    rstate = repo.state()

    if rstate == RepositoryState.REBASE_INTERACTIVE:
        info = repo.rebase_info()
        phrase1 = _("Rebasing {0} onto {1}",
                     tquoe(info.head_shorthand),
                     tquoe(shortHash(info.onto, maybe=True)))
        phrase2 = _("Currently stopped at {0}",
                     tquoe(shortHash(info.stopped_sha, maybe=True)))
        phrase3 = _("Your input is needed to continue.")
        return f"({info.msgnum}/{info.end}) {phrase1}. {phrase2}. {phrase3}"

    if rstate == RepositoryState.NONE:
        return _("Finished rebasing {0} onto {1}.",
                 tquoe(previousInfo.head_shorthand),
                 tquoe(shortHash(previousInfo.onto, maybe=True)))

    # Not translating this one because it's an error
    return f"Rebase stopped with state {rstate}."


class InteractiveRebase(RepoTask):
    allowProcessDialog = Signal(bool)

    dialog: RebaseDialog
    server: GFIpcServer
    todoFilePath: str
    currentSocket: QLocalSocket | None
    rebaseInfoAtStart: RebaseInfo | None

    def prereqs(self):
        # TODO: need clean workdir, too
        return TaskPrereqs.NoConflicts | TaskPrereqs.NoUnborn | TaskPrereqs.NoCherrypick

    def broadcastProcesses(self) -> bool:
        # TODO: must be able to override processdialog on the fly
        return False

    def setProcessDialogAllowed(self, visible: bool):
        # TODO: do something
        pass

    def flow(self, rootCommit: Oid):
        self.todoFilePath = ""
        self.currentSocket = None
        self.rebaseInfoAtStart = None

        dialog = RebaseDialog(self.parentWidget())
        dialog.finished.connect(lambda: self.setProcessDialogAllowed(True))
        dialog.accepted.connect(self.onDialogAccepted)
        dialog.rejected.connect(self.onDialogRejected)

        server = GFIpcServer(self, singleShot=True, startNow=True)
        server.clientConnected.connect(self.onClientConnected)

        self.dialog = dialog
        self.server = server

        env = {
            "GIT_SEQUENCE_EDITOR": server.clientCommand(),
        }

        # TODO: DON'T wait for finished synchronously!
        yield from self.flowCallGit(
            "-c", "core.abbrev=no",
            "rebase", "-i", str(rootCommit),
            # "--keep-base",
            env=env,
        )

        assert self.rebaseInfoAtStart is not None
        self.epilog.status = _rebaseEpilogStatus(self.repo, self.rebaseInfoAtStart)  # type: ignore[unreachable] # mypy is incorrect here

    def dumpSequenceAndDisconnect(self, sequenceText: str):
        assert self.todoFilePath

        text = self.dialog.serializeSequence()
        Path(self.todoFilePath).write_text(text, encoding="utf-8")

        GFIpcProtocol.writeMessage(self.currentSocket, GFIpcProtocol.Response())

        self.currentSocket.disconnectFromServer()
        self.currentSocket.waitForDisconnected(GFIpcProtocol.FastTimeout)

    def onDialogAccepted(self):
        text = self.dialog.serializeSequence()
        self.dumpSequenceAndDisconnect(text)

    def onDialogRejected(self):
        assert self.todoFilePath

        # Write empty sequence file
        Path(self.todoFilePath).write_text("\n", encoding="utf-8")

        self.currentSocket.disconnectFromServer()
        self.currentSocket.waitForDisconnected(GFIpcProtocol.FastTimeout)

    def onClientConnected(self, handshake: GFIpcProtocol.Handshake, socket: QLocalSocket):
        self.currentSocket = socket

        path = handshake.args[0]
        self.todoFilePath = path
        self.epilog.effects |= TaskEffects.Head

        text = Path(path).read_text(encoding="utf-8")
        sequence = parseRebaseTodo(text)

        self.dialog.setSequence(sequence)

        # Get info about the rebase for UI text
        info = self.repo.rebase_info(path)

        self.dialog.setWindowTitle(_("Rebase {0} onto {1}",
                                     tquoe(info.head_shorthand),
                                     tquoe(shortHash(info.onto, maybe=True))))

        # Prepare epilog message in case of success.
        # We'll override it if we're still in a rebase state after the dialog is closed.
        self.rebaseInfoAtStart = info

        self.dialog.show()


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

        self.epilog.effects |= TaskEffects.Head | TaskEffects.Workdir
        yield from self.flowCallGit("rebase", "--abort")

        self.epilog.status = _("Rebase aborted.")


class ContinueRebase(RepoTask):
    def flow(self):
        assert self.repo.state() == RepositoryState.REBASE_INTERACTIVE, \
            f"attempting to continue from state {self.repo.state()}"

        rebaseInfoAtStart = self.repo.rebase_info()

        self.epilog.effects |= TaskEffects.Head | TaskEffects.Workdir
        yield from self.flowCallGit("rebase", "--continue")

        self.epilog.status = _rebaseEpilogStatus(self.repo, rebaseInfoAtStart)
