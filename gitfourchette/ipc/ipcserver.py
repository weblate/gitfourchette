# -----------------------------------------------------------------------------
# Copyright (C) 2026 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

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
    clientConnected = Signal(dict, QLocalSocket)
    _globalSocketCounter = 0

    socketPath: str

    def __init__(self, parent: QObject, singleShot: bool, startNow: bool = True):
        super().__init__(parent)

        self.socketNumber = GFIpcServer._globalSocketCounter
        GFIpcServer._globalSocketCounter += 1
        self.socketPath = str(Path(qTempDir(), f"ipc{self.socketNumber}.sock"))
        self.singleShot = singleShot

        self.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.setMaxPendingConnections(1)
        self.newConnection.connect(self.onNewConnection)

        if startNow:
            doesListen = self.listenOnSocketPath()
            logger.debug(f"IPC server listening on {self.socketPath}: {doesListen} -- {self.fullServerName()}")
            assert doesListen

    def listenOnSocketPath(self) -> bool:
        return self.listen(self.socketPath)

    def onNewConnection(self):
        socket: QLocalSocket | None = self.nextPendingConnection()
        assert socket is not None
        logger.debug(f"New connection on {socket.fullServerName()}")
        assert socket.isValid()
        assert socket.isOpen()

        # Single-shot server: Stop listening for any additional connections
        if self.singleShot:
            self.close()

        # Get handshake from client
        payload = GFIpcProtocol.readMessage(socket, timeout=GFIpcProtocol.FastTimeout)
        if "args" not in payload:
            logger.warning("invalid payload from client")
            socket.close()
            return

        logger.debug(f"Got client handshake: {payload}")
        self.clientConnected.emit(payload, socket)

    def clientCommand(self, askpass: bool = False) -> str:
        """
        Return a command starting an IPC client that connects to this server.
        """

        sandbox = settings.prefs.isGitSandboxed()
        infix1 = f"ask{self.socketNumber}" if askpass else ""
        infix2 = "s" if sandbox else ""
        fileName = f"ipc{infix1}{infix2}.sh"
        launcherScript = Path(qTempDir(), fileName)

        if not launcherScript.exists():
            scriptText = self._clientScript(sandbox, askpass)
            launcherScript.write_text(scriptText, "utf-8")
            launcherScript.chmod(0o500)

        if askpass:
            return str(launcherScript)
        else:
            return shlex.join([str(launcherScript), self.socketPath])

    def _clientScript(self, sandbox: bool, askpass: bool) -> str:
        module = GFIpcProtocol.__module__
        tokens = ToolCommands.spawnNewInstance(module, sandbox=sandbox)

        # Using sys.path instead of PYTHONPATH because the latter may be empty in unit tests
        paths = sys.path[:]
        with suppress(ValueError):
            paths.remove("")  # disallow empty path (current working directory)
        pythonpath = shlex.quote(os.pathsep.join(paths))

        inargs = []
        if askpass:
            inargs.append("--askpass")
            inargs.append(shlex.quote(self.socketPath))
            inargs.append("--")

        return (
            '#!/usr/bin/env bash\n'
            f'export PYTHONPATH={pythonpath}\n'
            f'exec {shlex.join(tokens)} {" ".join(inargs)} "$@"\n'
        )
