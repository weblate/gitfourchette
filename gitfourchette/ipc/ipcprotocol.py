# -----------------------------------------------------------------------------
# Copyright (C) 2026 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

import argparse
import json
import os
import shlex
import sys

from gitfourchette.qt import *


class GFIpcProtocol:
    FastTimeout = 5000  # timeout for "instantaneous" client/server comms
    UserTimeout = -1  # timeout when waiting for user input
    MaxPayloadSize = 4096

    ProtocolVersionKey = "_protocol"
    ProtocolVersionValue = APP_VERSION

    @classmethod
    def writeMessage(cls, socket: QLocalSocket, payloadObj: dict[str, str]) -> int:
        """
        Serialize a dict over the socket.
        """

        # Inject version
        payloadObj = payloadObj.copy()
        payloadObj[cls.ProtocolVersionKey] = cls.ProtocolVersionValue

        payload = json.dumps(payloadObj).encode("utf-8", errors="replace")
        return socket.write(payload)

    @classmethod
    def readMessage(cls, socket: QLocalSocket) -> dict[str, str]:
        """
        Deserialize a dict from the socket.
        May raise TimeoutError if the message couldn't be read in due time,
        or ValueError if the payload doesn't honor protocol.
        """

        assert socket.bytesAvailable() > 0, "did you forget to wait for readyRead?"

        payload = socket.read(cls.MaxPayloadSize)
        if PYSIDE6:
            payload = bytes(payload)
        assert isinstance(payload, bytes)
        payloadObj = json.loads(payload)  # may raise JSONDecodeError (=ValueError)

        payloadVersion = payloadObj.get(cls.ProtocolVersionKey, "???")
        if payloadVersion != cls.ProtocolVersionValue:
            raise ValueError(f"incompatible protocol version '{payloadVersion}' (expected: '{cls.ProtocolVersionValue}')")

        return payloadObj

    @classmethod
    def simpleBlockingClient(
            cls,
            socketPath: str,
            handshakeObj: dict[str, str],
            fastTimeout: int = FastTimeout,
            responseTimeout: int = UserTimeout,
            parent=None,
    ) -> dict[str, str]:
        """
        Connect to a server, send a handshake, get the response, disconnect.
        Return the response as a dict.
        WARNING: This blocks the main thread, so don't use this if the UI is running.
        """

        socket = QLocalSocket(parent)
        socket.connectToServer(socketPath)

        try:
            if not socket.waitForConnected(fastTimeout):
                raise TimeoutError(f"timed out waiting for connection - {socket.errorString()}")

            cls.writeMessage(socket, handshakeObj)

            if not socket.waitForBytesWritten(fastTimeout):
                raise TimeoutError(f"timed out waiting for writing - {socket.errorString()}")

            if not socket.waitForReadyRead(responseTimeout):
                raise TimeoutError(f"timed out waiting for server response - {socket.errorString()}")

            responseObj = cls.readMessage(socket)
        finally:
            socket.disconnectFromServer()
            socket.deleteLater()

        if "print" in responseObj:
            print(responseObj["print"], flush=True)

        if "abort" in responseObj:
            print(responseObj["abort"], file=sys.stderr)
            sys.exit(1)

        return responseObj

    @classmethod
    def clientMain(cls):
        parser = argparse.ArgumentParser()
        parser.add_argument("--askpass", action="store_true")
        parser.add_argument("socket")
        parser.add_argument("forward", nargs="*",
                            help="forward arguments, typically askpass")
        args = parser.parse_args()

        if args.askpass:
            forwardedArgs = " ".join(args.forward)
        else:
            forwardedArgs = shlex.join(args.forward)

        handshakeObj = {"args": forwardedArgs}
        if args.askpass:
            for var in ["SSH_ASKPASS_PROMPT", "SSH_AUTH_SOCK", "SSH_AGENT_PID"]:
                handshakeObj[var] = os.environ.get(var, "")

        return cls.simpleBlockingClient(args.socket, handshakeObj)


if __name__ == '__main__':
    GFIpcProtocol.clientMain()
