from gitfourchette import log
from gitfourchette import repoconfig
from gitfourchette.porcelain import *
from gitfourchette.qt import *
from gitfourchette.toolbox import *
import base64
import os.path
import re


DLRATE_REFRESH_INTERVAL = 1000


AUTH_NAMES = {
    GIT_CREDENTIAL_USERPASS_PLAINTEXT: "userpass_plaintext",
    GIT_CREDENTIAL_SSH_KEY: "ssh_key",
    GIT_CREDENTIAL_SSH_CUSTOM: "ssh_custom",
    GIT_CREDENTIAL_DEFAULT: "default",
    GIT_CREDENTIAL_SSH_INTERACTIVE: "ssh_interactive",
    GIT_CREDENTIAL_USERNAME: "username",
    GIT_CREDENTIAL_SSH_MEMORY: "ssh_memory"
}


def getAuthNamesFromFlags(allowedTypes):
    allowedTypeNames = []
    for k, v in AUTH_NAMES.items():
        if allowedTypes & k:
            allowedTypeNames.append(v)
    return ", ".join(allowedTypeNames)


def isPrivateKeyPassphraseProtected(path: str):
    with open(path, "rt") as f:
        lines = f.read().splitlines(False)

    while lines and not re.match("^-+END OPENSSH PRIVATE KEY-+ *$", lines.pop()):
        continue

    while lines and not re.match("^-+BEGIN OPENSSH PRIVATE KEY-+ *$", lines.pop(0)):
        continue

    if not lines:
        return False

    keyContents = base64.b64decode("".join(lines))

    return b"bcrypt" in keyContents


class RemoteLink(QObject, RemoteCallbacks):
    userAbort = Signal()
    message = Signal(str)
    progress = Signal(int, int)

    @staticmethod
    def mayAbortNetworkOperation(f):
        def wrapper(*args):
            x: RemoteLink = args[0]
            if x._aborting:
                raise InterruptedError(translate("RemoteLink", "Remote operation interrupted by user."))
            return f(*args)
        return wrapper

    def __init__(self, parent: QObject):
        QObject.__init__(self, parent)
        RemoteCallbacks.__init__(self)

        self.setObjectName("RemoteLink")

        self.attempts = 0

        self.keypairFiles = []
        self.usingCustomKeyFile = ""

        self.downloadRateTimer = QElapsedTimer()
        self.downloadRate = 0
        self.receivedBytesOnTimerStart = 0

        self.userAbort.connect(self._onAbort)

        self._aborting = False
        self._sidebandProgressBuffer = ""

        self.anyKeyIsPassphraseProtected = False
        self.anyKeyIsUnreadable = False

    def discoverKeyFiles(self, remote: Remote | None = None):
        # Find remote-specific key files
        if remote:
            privkey = repoconfig.getRemoteKeyFile(remote._repo, remote.name)
            self.usingCustomKeyFile = privkey
            if privkey:
                pubkey = privkey + ".pub"
                self.keypairFiles.append((pubkey, privkey))

                if not os.path.isfile(pubkey):
                    raise FileNotFoundError(self.tr("Remote-specific public key file not found:") + " " + compactPath(pubkey))

                if not os.path.isfile(privkey):
                    raise FileNotFoundError(self.tr("Remote-specific private key file not found:") + " " + compactPath(privkey))

                log.info("RemoteLink", "Using remote-specific key pair", privkey)

                self.keypairFiles.append((pubkey, privkey))

        # Find user key files
        if not self.usingCustomKeyFile:
            sshDirectory = QStandardPaths.locate(QStandardPaths.StandardLocation.HomeLocation, ".ssh", QStandardPaths.LocateOption.LocateDirectory)
            if sshDirectory:
                for file in os.listdir(sshDirectory):
                    pubkey = os.path.join(sshDirectory, file)
                    if pubkey.endswith(".pub"):
                        privkey = pubkey.removesuffix(".pub")
                        if os.path.isfile(privkey) and os.path.isfile(pubkey):
                            log.info("RemoteLink", "Discovered key pair", privkey)
                            self.keypairFiles.append((pubkey, privkey))

        # See if any of the keys are passphrase-protected or unreadable
        for pubkey, privkey in self.keypairFiles:
            try:
                if isPrivateKeyPassphraseProtected(privkey):
                    self.anyKeyIsPassphraseProtected = True
            except IOError:
                self.anyKeyIsUnreadable = True

    def isAborting(self):
        return self._aborting

    def raiseAbortFlag(self):
        self.message.emit(self.tr("Aborting remote operation..."))
        self.progress.emit(0, 0)
        self.userAbort.emit()

    def _onAbort(self):
        self._aborting = True
        log.info("RemoteLink", "Abort flag set.")

    @mayAbortNetworkOperation
    def sideband_progress(self, string):
        # The remote sends a stream of characters intended to be printed
        # progressively. So, the string we receive may be incomplete.
        string = self._sidebandProgressBuffer + string

        # \r refreshes the current status line, and \n starts a new one.
        # Send the last complete line we have.
        split = string.replace("\r", "\n").rsplit("\n", 2)
        try:
            self.message.emit(self.tr("Remote:", "message from remote") + " " + split[-2])
        except IndexError:
            pass

        # Buffer partial message for next time.
        self._sidebandProgressBuffer = split[-1]

    # def certificate_check(self, certificate, valid, host):
    #     gflog("RemoteLink", "Certificate Check", certificate, valid, host)
    #     return 1

    @mayAbortNetworkOperation
    def credentials(self, url, username_from_url, allowed_types):
        self.attempts += 1

        if self.attempts > 10:
            raise ConnectionRefusedError(self.tr("Too many credential retries."))

        if self.attempts == 1:
            log.info("RemoteLink", "Auths accepted by server:", getAuthNamesFromFlags(allowed_types))

        if self.keypairFiles and (allowed_types & GIT_CREDENTIAL_SSH_KEY):
            pubkey, privkey = self.keypairFiles.pop()
            log.info("RemoteLink", "Attempting login with:", compactPath(pubkey))

            if self.usingCustomKeyFile:
                self.message.emit(self.tr("Logging in with remote-specific key...") + "\n" + compactPath(pubkey))
            else:
                self.message.emit(self.tr("Attempting login...") + "\n" + compactPath(pubkey))

            return Keypair(username_from_url, pubkey, privkey, "")
            # return KeypairFromAgent(username_from_url)
        elif self.attempts == 0:
            raise NotImplementedError(
                self.tr("Unsupported authentication type.") + " " +
                self.tr("The remote claims to accept: {0}.").format(getAuthNamesFromFlags(allowed_types)))
        elif self.anyKeyIsUnreadable:
            raise ConnectionRefusedError(
                self.tr("Could not find suitable key files for this remote.") + " " +
                self.tr("The key files couldn’t be opened (permission issues?)."))
        elif self.anyKeyIsPassphraseProtected:
            raise ConnectionRefusedError(
                self.tr("Could not find suitable key files for this remote.") + " " +
                self.tr("Please note that {0} does not support passphrase-protected private keys yet. "
                        "You may have better luck with a decrypted private key.").format(qAppName()))
        elif self.usingCustomKeyFile:
            raise ConnectionRefusedError(self.tr(
                "The remote has rejected your custom key file ({0}). "
                "To change key file settings for this remote, "
                "right-click on the remote in the sidebar and pick “Edit Remote”."
            ).format(compactPath(self.usingCustomKeyFile)))
        else:
            raise ConnectionRefusedError(self.tr("Credentials rejected by remote."))

    @mayAbortNetworkOperation
    def transfer_progress(self, stats: TransferProgress):
        if not self.downloadRateTimer.isValid():
            self.downloadRateTimer.start()
            self.receivedBytesOnTimerStart = stats.received_bytes
        elif self.downloadRateTimer.elapsed() > DLRATE_REFRESH_INTERVAL:
            self.downloadRate = (stats.received_bytes - self.receivedBytesOnTimerStart) * 1000 // DLRATE_REFRESH_INTERVAL
            self.downloadRateTimer.restart()
            self.receivedBytesOnTimerStart = stats.received_bytes
        else:
            # Don't update UI too frequently (ease CPU load)
            return

        obj = min(stats.indexed_objects, stats.total_objects)
        if obj == stats.total_objects:
            self.progress.emit(0, 0)
        else:
            self.progress.emit(obj, stats.total_objects)

        locale = QLocale()

        objectsReadyText = self.tr("{0} of {1} objects ready.").format(
            locale.toString(obj),
            locale.toString(stats.total_objects))
        dataSizeText = locale.formattedDataSize(stats.received_bytes)
        downloadRateText = locale.formattedDataSize(self.downloadRate)

        message = objectsReadyText + "\n"

        if stats.received_objects == stats.total_objects:
            message += self.tr("{0} total. Indexing...", "e.g. '12 MB total'").format(dataSizeText)
        else:
            message += self.tr("{0} received.", "e.g. '12 MB received so far'").format(dataSizeText)
            if self.downloadRate != 0:
                message += " " + self.tr("({0}/s)", "e.g. 1 MB per second").format(downloadRateText)
        self.message.emit(message)

    def update_tips(self, refname, old, new):
        log.info("RemoteLink", F"Update tip {refname}: {old} ---> {new}")

    def push_update_reference(self, refname: str, message: str | None):
        if not message:
            message = ""
        self.message.emit(self.tr("Push update reference:") + f"\n{refname} {message}")
