# -----------------------------------------------------------------------------
# Copyright (C) 2026 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

import os
import sys
from enum import StrEnum

from gitfourchette import pycompat  # noqa: F401 - StrEnum for Python 3.10
from gitfourchette.qt import QLocalSocket


class GFIpcProtocol:
    EnvKey = "_GITFOURCHETTE_IPCKEY"

    FastTimeout = 5000  # timeout for "instantaneous" client/server comms
    UserTimeout = -1  # timeout when waiting for user input

    TagLength = 1

    class MessageTag(StrEnum):
        ClientHandshake = "C"
        ServerReply = "S"
        Abort = "A"

    @classmethod
    def writeMessage(cls, socket: QLocalSocket, tag: MessageTag, text: str = ""):
        assert len(tag) == cls.TagLength
        payload = (tag + text).encode("utf-8", errors="replace")
        socket.write(payload)
        didWrite = socket.waitForBytesWritten(cls.FastTimeout)
        if not didWrite:
            raise TimeoutError(f"timed out writing on socket - {socket.errorString()}")

    @classmethod
    def readMessage(cls, socket: QLocalSocket, timeout: int) -> tuple[MessageTag, str]:
        if not socket.waitForReadyRead(timeout):
            raise TimeoutError(f"timed out ({timeout} ms) waiting for data on socket - {socket.errorString()}")

        payload = socket.readAll().data().decode("utf-8", errors="replace")
        tag = cls.MessageTag(payload[0 : cls.TagLength])
        text = payload[cls.TagLength:]
        return tag, text

    @classmethod
    def clientMain(cls):
        serverKey = os.environ[cls.EnvKey]
        handshakePayload = " ".join(sys.argv[1:])

        socket = QLocalSocket(None)
        socket.connectToServer(serverKey)
        if not socket.waitForConnected(cls.FastTimeout):
            raise TimeoutError(f"timed out waiting for connection - {socket.errorString()}")

        cls.writeMessage(socket, cls.MessageTag.ClientHandshake, handshakePayload)

        tag, replyPayload = cls.readMessage(socket, timeout=cls.UserTimeout)
        if tag != cls.MessageTag.ServerReply:
            raise ValueError(f"unexpected server reply tag: {tag}")

        socket.disconnectFromServer()
        socket.deleteLater()

        if replyPayload:
            print(replyPayload, flush=True)


if __name__ == '__main__':
    GFIpcProtocol.clientMain()
