# -----------------------------------------------------------------------------
# Copyright (C) 2026 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

import argparse
import json
import os
import sys

from gitfourchette.qt import QLocalSocket, PYSIDE6


class GFIpcProtocol:
    FastTimeout = 5000  # timeout for "instantaneous" client/server comms
    UserTimeout = -1  # timeout when waiting for user input
    MaxPayloadSize = 4096

    @classmethod
    def writeMessage(cls, socket: QLocalSocket, payloadObj: dict[str, str]):
        payload = json.dumps(payloadObj).encode("utf-8", errors="replace")
        socket.write(payload)
        didWrite = socket.waitForBytesWritten(cls.FastTimeout)
        if not didWrite:
            raise TimeoutError(f"timed out writing on socket - {socket.errorString()}")

    @classmethod
    def readMessage(cls, socket: QLocalSocket, timeout: int) -> dict[str, str]:
        if not socket.waitForReadyRead(timeout):
            raise TimeoutError(f"timed out waiting for data on socket - {socket.errorString()}")

        payload = socket.read(cls.MaxPayloadSize)
        if PYSIDE6:
            payload = bytes(payload)
        assert isinstance(payload, bytes)
        payloadObj = json.loads(payload)
        return payloadObj

    @classmethod
    def clientMain(cls):
        parser = argparse.ArgumentParser()
        parser.add_argument("--askpass", action="store_true")
        parser.add_argument("socket")
        parser.add_argument("forward", nargs="*")
        args = parser.parse_args()

        socket = QLocalSocket(None)
        socket.connectToServer(args.socket)
        if not socket.waitForConnected(cls.FastTimeout):
            raise TimeoutError(f"timed out waiting for connection - {socket.errorString()}")

        handshakeObj = {"args": " ".join(args.forward)}
        if args.askpass:
            for var in ["SSH_ASKPASS_PROMPT", "SSH_AUTH_SOCK", "SSH_AGENT_PID"]:
                handshakeObj[var] = os.environ.get(var, "")

        cls.writeMessage(socket, handshakeObj)
        responseObj = cls.readMessage(socket, timeout=cls.UserTimeout)

        socket.disconnectFromServer()
        socket.deleteLater()

        if "print" in responseObj:
            print(responseObj["print"], flush=True)

        if "abort" in responseObj:
            print(responseObj["abort"], file=sys.stderr)
            sys.exit(1)


if __name__ == '__main__':
    GFIpcProtocol.clientMain()
