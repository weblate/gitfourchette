# -----------------------------------------------------------------------------
# Copyright (C) 2026 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

import base64
import logging
import os
import shlex
import sys
from contextlib import suppress
from pathlib import Path

from gitfourchette import settings
from gitfourchette.exttools.toolcommands import ToolCommands
from gitfourchette.ipc.ipcprotocol import GFIpcProtocol
from gitfourchette.qt import *

logger = logging.getLogger(__name__)


class GFIpcServer(QLocalServer):
    clientConnected = Signal(str)

    currentConnection: QLocalSocket | None
    serverKey: str

    def __init__(self, parent: QObject):
        super().__init__(parent)
        self.currentConnection = None

        randomBlob = base64.urlsafe_b64encode(os.urandom(12)).decode("ascii")
        self.serverKey = f"{APP_SYSTEM_NAME}_{randomBlob}"

        self.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.setMaxPendingConnections(1)
        self.newConnection.connect(self.onNewConnection)

        doesListen = self.listen(self.serverKey)
        logger.debug(f"IPC server listening on {self.serverKey}: {doesListen} -- {self.fullServerName()}")
        assert doesListen

    def onNewConnection(self):
        socket: QLocalSocket | None = self.nextPendingConnection()
        assert socket is not None
        logger.debug(f"New connection on {socket.fullServerName()}")

        # Single-shot server: Stop listening for any additional connections
        self.close()

        # Get handshake from client
        tag, payload = GFIpcProtocol.readMessage(socket, timeout=GFIpcProtocol.FastTimeout)
        if tag != GFIpcProtocol.MessageTag.ClientHandshake:
            logger.warning(f"unexpected tag: {tag}")
            socket.close()
            return

        logger.debug(f"Got client handshake: {payload}")
        self.currentConnection = socket
        self.clientConnected.emit(payload)

    def writeAndDisconnect(self, tag: GFIpcProtocol.MessageTag, payload: str = ""):
        assert self.currentConnection is not None
        GFIpcProtocol.writeMessage(self.currentConnection, tag, payload)
        self.currentConnection.disconnectFromServer()
        self.currentConnection = None

    def replyAndDisconnect(self, payload: str = ""):
        self.writeAndDisconnect(GFIpcProtocol.MessageTag.ServerReply, payload)

    def gitEnvironmentForClient(self, varName: str):
        """
        Return a dict of environment variables that should be passed to git so
        it can start an IPC client.

        varName is the name of the environment variable that git will use,
        e.g. GIT_SEQUENCE_EDITOR.
        """

        sandbox = settings.prefs.isGitSandboxed()
        fileName = "ipc_sandboxed.sh" if sandbox else "ipc.sh"
        launcherScript = Path(qTempDir(), fileName)

        if not launcherScript.exists():
            module = GFIpcProtocol.__module__
            tokens = ToolCommands.spawnNewInstance(module, sandbox=sandbox)

            # Using sys.path instead of PYTHONPATH because the latter may be empty in unit tests
            paths = sys.path[:]
            with suppress(ValueError):
                paths.remove("")  # disallow empty path (current working directory)
            pythonpath = shlex.quote(os.pathsep.join(paths))

            # Discard stderr to avoid forwarding Qt error spam to ProcessDialog.
            script = (
                '#!/usr/bin/env bash\n'
                f'export PYTHONPATH={pythonpath}\n'
                f'exec {shlex.join(tokens)} "$@"\n'  # 2>/dev/null\n')
            )

            launcherScript.write_text(script, "utf-8")
            launcherScript.chmod(0o500)

        return {
            varName: str(launcherScript),
            GFIpcProtocol.EnvKey: self.serverKey,
        }
