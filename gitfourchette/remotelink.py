from gitfourchette import log
from gitfourchette.qt import QStandardPaths, QObject, Signal, QElapsedTimer, QLocale
from gitfourchette.util import compactPath
import os.path
import pygit2


DLRATE_REFRESH_INTERVAL = 1000


PRIVATE_KEY_FILES = [
    "id_ed25519",
    "id_rsa",
]


AUTH_NAMES = {
    pygit2.GIT_CREDENTIAL_USERPASS_PLAINTEXT: "userpass_plaintext",
    pygit2.GIT_CREDENTIAL_SSH_KEY: "ssh_key",
    pygit2.GIT_CREDENTIAL_SSH_CUSTOM: "ssh_custom",
    pygit2.GIT_CREDENTIAL_DEFAULT: "default",
    pygit2.GIT_CREDENTIAL_SSH_INTERACTIVE: "ssh_interactive",
    pygit2.GIT_CREDENTIAL_USERNAME: "username",
    pygit2.GIT_CREDENTIAL_SSH_MEMORY: "ssh_memory"
}


def getAuthNamesFromFlags(allowedTypes):
    allowedTypeNames = []
    for k, v in AUTH_NAMES.items():
        if allowedTypes & k:
            allowedTypeNames.append(v)
    return ", ".join(allowedTypeNames)


class RemoteLinkSignals(QObject):
    userAbort = Signal()
    message = Signal(str)
    progress = Signal(int, int)


class RemoteLink(pygit2.RemoteCallbacks):
    def __init__(self):
        self.attempts = 0
        self.signals = RemoteLinkSignals()

        self.keypairFiles = []
        sshDirectory = QStandardPaths.locate(QStandardPaths.HomeLocation, ".ssh", QStandardPaths.LocateDirectory)
        if sshDirectory:
            for file in PRIVATE_KEY_FILES:
                privkey = os.path.join(sshDirectory, file)
                pubkey = privkey + ".pub"
                if os.path.isfile(privkey) and os.path.isfile(pubkey):
                    log.info("RemoteLink", "Discovered key pair", privkey)
                    self.keypairFiles.append((pubkey, privkey))

        self.downloadRateTimer = QElapsedTimer()
        self.downloadRate = 0
        self.receivedBytesOnTimerStart = 0

        self.signals.userAbort.connect(self._onAbort)

        self._aborting = False
        self._sidebandProgressBuffer = ""

    def isAborting(self):
        return self._aborting

    def raiseAbortFlag(self):
        self.signals.message.emit("Aborting...")
        self.signals.progress.emit(0, 0)
        self.signals.userAbort.emit()

    def _onAbort(self):
        self._aborting = True

    def sideband_progress(self, string):
        # The remote sends a stream of characters intended to be printed
        # progressively. So, the string we receive may be incomplete.
        string = self._sidebandProgressBuffer + string

        # \r refreshes the current status line, and \n starts a new one.
        # Send the last complete line we have.
        split = string.replace("\r", "\n").rsplit("\n", 2)
        try:
            self.signals.message.emit("Remote: " + split[-2])
        except IndexError:
            pass

        # Buffer partial message for next time.
        self._sidebandProgressBuffer = split[-1]

    # def certificate_check(self, certificate, valid, host):
    #     gflog("RemoteLink", "Certificate Check", certificate, valid, host)
    #     return 1

    def credentials(self, url, username_from_url, allowed_types):
        if self._aborting:
            raise InterruptedError("User interrupted login.")

        self.attempts += 1

        if self.attempts > 10:
            raise ConnectionRefusedError("Too many credential retries.")

        if self.attempts == 1:
            log.info("RemoteLink", "Auths accepted by server:", getAuthNamesFromFlags(allowed_types))

        if self.keypairFiles and (allowed_types & pygit2.credentials.GIT_CREDENTIAL_SSH_KEY):
            pubkey, privkey = self.keypairFiles.pop()
            log.info("RemoteLink", "Attempting login with:", compactPath(pubkey))
            self.signals.message.emit(F"Attempting login...\n{compactPath(pubkey)}")
            return pygit2.Keypair(username_from_url, pubkey, privkey, "")
            # return pygit2.KeypairFromAgent(username_from_url)
        else:
            if self.attempts > 1:
                raise ConnectionRefusedError(F"Credentials rejected by remote. The remote claims to accept: {getAuthNamesFromFlags(allowed_types)}.")
            else:
                raise NotImplementedError(F"Unsupported auth type. The remote claims to accept: {getAuthNamesFromFlags(allowed_types)}.")

    def transfer_progress(self, stats: pygit2.remote.TransferProgress):
        if self._aborting:
            raise InterruptedError("User interrupted transfer.")

        if not self.downloadRateTimer.isValid():
            self.downloadRateTimer.start()
            self.receivedBytesOnTimerStart = stats.received_bytes
        elif self.downloadRateTimer.elapsed() > DLRATE_REFRESH_INTERVAL:
            self.downloadRate = (stats.received_bytes - self.receivedBytesOnTimerStart) * 1000 // DLRATE_REFRESH_INTERVAL
            self.downloadRateTimer.restart()
            self.receivedBytesOnTimerStart = stats.received_bytes

        obj = min(stats.indexed_objects, stats.total_objects)
        if obj == stats.total_objects:
            self.signals.progress.emit(0, 0)
        else:
            self.signals.progress.emit(obj, stats.total_objects)

        locale = QLocale.system()

        message = (
            F"{obj:,} of {stats.total_objects:,} objects ready\n"
            + locale.formattedDataSize(stats.received_bytes))

        if stats.received_objects == stats.total_objects:
            message += " total. Indexing..."
        else:
            message += " received"
            if self.downloadRate != 0:
                message += F" - {locale.formattedDataSize(self.downloadRate)}/s"
        self.signals.message.emit(message)

    def update_tips(self, refname, old, new):
        log.info("RemoteLink", F"Update tip {refname}: {old} ---> {new}")

    def push_update_reference(self, refname, message):
        self.signals.message.emit(F"Push update ref {refname} {message}")
