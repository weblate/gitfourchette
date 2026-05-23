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
from gitfourchette.porcelain import Oid, RefPrefix
from gitfourchette.ipc.ipcserver import GFIpcServer
from gitfourchette.qt import *
from gitfourchette.rebase.rebasemodel import parseRebaseTodo
from gitfourchette.tasks import TaskPrereqs, TaskEffects
from gitfourchette.tasks.repotask import RepoTask
from gitfourchette.toolbox import shortHash, tquoe

logger = logging.getLogger(__name__)


class InteractiveRebase(RepoTask):
    allowProcessDialog = Signal(bool)

    dialog: RebaseDialog
    server: GFIpcServer
    todoFilePath: str

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

    def onDialogAccepted(self):
        assert self.todoFilePath

        text = self.dialog.serializeSequence()
        Path(self.todoFilePath).write_text(text, encoding="utf-8")

        GFIpcProtocol.writeMessage(self.currentSocket, GFIpcProtocol.Response())

        self.currentSocket.disconnectFromServer()
        self.currentSocket.waitForDisconnected(GFIpcProtocol.FastTimeout)

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

        # Get head name
        # TODO: Can we get those from pygit2?
        try:
            headName = Path(path).with_name("head-name").read_text("utf-8").strip()
            _dummy, headName = RefPrefix.split(headName)
        except OSError:
            headName = ""

        # Get 'onto' name
        try:
            onto = Path(path).with_name("onto").read_text("utf-8").strip()
            # If it's a hash, shorten it; otherwise it's probably a ref name
            if all(c in "0123456789abcdef" for c in onto):
                onto = shortHash(onto)
        except OSError:
            onto = ""

        if headName and onto:
            self.dialog.setWindowTitle(_("Rebase {0} onto {1}", tquoe(headName), tquoe(onto)))

        self.epilog.status = _("Rebased {0} onto {1}.", tquoe(headName), tquoe(onto))

        self.dialog.show()
