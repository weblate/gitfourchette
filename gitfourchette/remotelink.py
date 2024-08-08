import base64
import logging
import os.path
import re
from contextlib import suppress

from gitfourchette import settings
from gitfourchette.forms.brandeddialog import showTextInputDialog
from gitfourchette.porcelain import *
from gitfourchette.qt import *
from gitfourchette.repoprefs import RepoPrefs
from gitfourchette.settings import TEST_MODE
from gitfourchette.toolbox import *

logger = logging.getLogger(__name__)

DLRATE_REFRESH_INTERVAL = 500


def getAuthNamesFromFlags(allowedTypes):
    allowedTypeNames = []
    for credential in CredentialType:
        if allowedTypes & credential:
            allowedTypeNames.append(credential.name.lower())
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


def collectUserKeyFiles():
    if TEST_MODE:
        from test.util import getTestDataPath
        sshDirectory = getTestDataPath("keys")
    else:  # pragma: no cover
        sshDirectory = QStandardPaths.locate(QStandardPaths.StandardLocation.HomeLocation, ".ssh", QStandardPaths.LocateOption.LocateDirectory)

    keypairFiles = []

    if not sshDirectory:
        return keypairFiles

    for file in os.listdir(sshDirectory):
        pubkey = os.path.join(sshDirectory, file)
        if pubkey.endswith(".pub"):
            privkey = pubkey.removesuffix(".pub")
            if os.path.isfile(privkey) and os.path.isfile(pubkey):
                logger.debug(f"Discovered key pair {privkey}")
                keypairFiles.append((pubkey, privkey))

    return keypairFiles


class RemoteLink(QObject, RemoteCallbacks):
    userAbort = Signal()
    message = Signal(str)
    progress = Signal(int, int)

    requestSecret = Signal(str)
    secretReady = Signal(str, str)

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

        assert findParentWidget(self)

        self.secretReady.connect(self.setAsyncSecret)
        self._asyncSecret = ""
        self._asyncSecretForKeyFile = ""
        self.requestSecret.connect(self.requestSecretUi)

        self.setObjectName("RemoteLink")
        self.userAbort.connect(self._onAbort)
        self.downloadRateTimer = QElapsedTimer()
        self.resetLoginState()

    def resetLoginState(self):
        self.attempts = 0

        self.keypairFiles = []
        self.usingCustomKeyFile = ""
        self.moreDetailsOnCustomKeyFileFail = True

        self.lastAttemptKey = ""
        self.lastAttemptUrl = ""
        self.usingKnownKeyFirst = False  # for informative purposes only

        self.downloadRate = 0
        self.receivedBytesOnTimerStart = 0
        self.downloadRateTimer.invalidate()

        self._aborting = False
        self._sidebandProgressBuffer = ""

        self.anyKeyIsUnreadable = False

    def forceCustomKeyFile(self, privKeyPath):
        self.usingCustomKeyFile = privKeyPath
        self.moreDetailsOnCustomKeyFileFail = False

    def discoverKeyFiles(self, remote: Remote | str = ""):
        # Find remote-specific key files
        if isinstance(remote, Remote) and not self.usingCustomKeyFile:
            self.usingCustomKeyFile = RepoPrefs.getRemoteKeyFileForRepo(remote._repo, remote.name)

        if self.usingCustomKeyFile:
            privkey = self.usingCustomKeyFile
            pubkey = privkey + ".pub"

            if not os.path.isfile(pubkey):
                raise FileNotFoundError(self.tr("Remote-specific public key file not found:") + " " + compactPath(pubkey))

            if not os.path.isfile(privkey):
                raise FileNotFoundError(self.tr("Remote-specific private key file not found:") + " " + compactPath(privkey))

            logger.info(f"Using remote-specific key pair {privkey}")

            self.keypairFiles.append((pubkey, privkey))

        # Find user key files
        else:
            self.keypairFiles.extend(collectUserKeyFiles())

            # If we've already connected to this host before,
            # give higher priority to the key that we used last
            if remote:
                url = remote.url if isinstance(remote, Remote) else remote
                assert type(url) is str
                strippedUrl = stripRemoteUrlPath(url)
                if strippedUrl and strippedUrl in settings.history.workingKeys:
                    workingKey = settings.history.workingKeys[strippedUrl]
                    self.keypairFiles.sort(key=lambda tup: tup[1] != workingKey)
                    logger.debug(f"Will try key '{workingKey}' first because it has been used in the past to access '{strippedUrl}'")
                    self.usingKnownKeyFirst = True

        # See if any of the keys are unreadable
        for pubkey, privkey in self.keypairFiles:
            try:
                # Just some dummy read
                isPrivateKeyPassphraseProtected(privkey)
            except IOError:
                self.anyKeyIsUnreadable = True
                break

    def isAborting(self):
        return self._aborting

    def raiseAbortFlag(self):
        self.message.emit(self.tr("Aborting remote operation..."))
        self.progress.emit(0, 0)
        self.userAbort.emit()

    def _onAbort(self):
        self._aborting = True
        logger.info("Abort flag set.")

    @mayAbortNetworkOperation
    def sideband_progress(self, string):
        # The remote sends a stream of characters intended to be printed
        # progressively. So, the string we receive may be incomplete.
        string = self._sidebandProgressBuffer + string

        # \r refreshes the current status line, and \n starts a new one.
        # Send the last complete line we have.
        split = string.replace("\r", "\n").rsplit("\n", 2)
        with suppress(IndexError):
            logger.info(f"[sideband] {split[-2]}")

        # Buffer partial message for next time.
        self._sidebandProgressBuffer = split[-1]

    # def certificate_check(self, certificate, valid, host):
    #     gflog("RemoteLink", "Certificate Check", certificate, valid, host)
    #     return 1

    @mayAbortNetworkOperation
    def credentials(self, url, username_from_url, allowed_types):
        self.attempts += 1
        self.lastAttemptKey = ""

        if self.attempts > 10:
            raise ConnectionRefusedError(self.tr("Too many credential retries."))

        if self.attempts == 1:
            logger.info(f"Auths accepted by server: {getAuthNamesFromFlags(allowed_types)}")

        if self.keypairFiles and (allowed_types & CredentialType.SSH_KEY):
            pubkey, privkey = self.keypairFiles.pop(0)
            logger.info(f"Logging in with: {compactPath(pubkey)}")

            if self.usingCustomKeyFile:
                self.message.emit(self.tr("Logging in with remote-specific key...") + "\n" + compactPath(pubkey))
            elif self.attempts == 1 and self.usingKnownKeyFirst:
                self.message.emit(self.tr("Logging in...") + "\n" + compactPath(pubkey))
            else:
                self.message.emit(self.tr("Attempting login...") + "\n" + compactPath(pubkey))

            secret = None
            if isPrivateKeyPassphraseProtected(privkey):
                secret = self.getAsyncSecret(privkey)

            self.lastAttemptKey = privkey
            self.lastAttemptUrl = url
            return Keypair(username_from_url, pubkey, privkey, secret)
            # return KeypairFromAgent(username_from_url)
        elif self.attempts == 0:
            raise NotImplementedError(
                self.tr("Unsupported authentication type.") + " " +
                self.tr("The remote claims to accept: {0}.").format(getAuthNamesFromFlags(allowed_types)))
        elif self.anyKeyIsUnreadable:
            raise ConnectionRefusedError(
                self.tr("Could not find suitable key files for this remote.") + " " +
                self.tr("The key files couldn’t be opened (permission issues?)."))
        elif self.usingCustomKeyFile:
            message = self.tr("The remote has rejected your custom key file ({0})."
                              ).format(compactPath(self.usingCustomKeyFile))
            if self.moreDetailsOnCustomKeyFileFail:
                message += " " + self.tr("To change key file settings for this remote, "
                                         "right-click on the remote in the sidebar and pick “Edit Remote”.")
            raise ConnectionRefusedError(message)
        else:
            raise ConnectionRefusedError(self.tr("Credentials rejected by remote."))

    @mayAbortNetworkOperation
    def transfer_progress(self, stats: TransferProgress):
        if not self.downloadRateTimer.isValid():
            self.downloadRateTimer.start()
            self.receivedBytesOnTimerStart = stats.received_bytes
        elif self.downloadRateTimer.elapsed() > DLRATE_REFRESH_INTERVAL:
            intervalBytes = stats.received_bytes - self.receivedBytesOnTimerStart
            self.downloadRate = int(intervalBytes * 1000 / self.downloadRateTimer.elapsed())
            self.downloadRateTimer.restart()
            self.receivedBytesOnTimerStart = stats.received_bytes
        else:
            # Don't update UI too frequently (ease CPU load)
            return

        obj = min(stats.received_objects, stats.total_objects)
        if obj == stats.total_objects:
            self.progress.emit(0, 0)
        else:
            self.progress.emit(obj, stats.total_objects)

        locale = QLocale()
        sizeText = locale.formattedDataSize(stats.received_bytes, 1)

        message = ""
        if stats.received_objects != stats.total_objects:
            message += self.tr("Downloading: {0}...").format(sizeText)
            if self.downloadRate != 0:
                rateText = locale.formattedDataSize(self.downloadRate, 0 if self.downloadRate < 1e6 else 1)
                message += "\n" + self.tr("({0}/s)", "download speed (per second)").format(rateText)
        else:
            message += self.tr("Download complete ({0}).").format(sizeText)
            message += "\n" + self.tr("Indexing {0} of {1} objects...").format(locale.toString(obj), locale.toString(stats.total_objects))

        self.message.emit(message)

    def update_tips(self, refname, old, new):
        logger.info(f"Update tip {refname}: {old} ---> {new}")

    def push_update_reference(self, refname: str, message: str | None):
        if not message:
            message = ""
        self.message.emit(self.tr("Push update reference:") + f"\n{refname} {message}")

    def rememberSuccessfulKeyFile(self):
        if self.lastAttemptKey and self.lastAttemptUrl and not self.usingCustomKeyFile:
            strippedUrl = stripRemoteUrlPath(self.lastAttemptUrl)
            settings.history.setRemoteWorkingKey(strippedUrl, self.lastAttemptKey)
            logger.debug(f"Remembering key '{self.lastAttemptKey}' for host '{strippedUrl}'")

    def remoteKeyFileContext(self, remote: Remote | str):
        return RemoteLinkKeyFileContext(self, remote)

    def setAsyncSecret(self, keyfile: str, secret: str):
        self._asyncSecret = secret
        self._asyncSecretForKeyFile = keyfile

    def getAsyncSecret(self, keyfile: str) -> str | None:
        assert not onAppThread()
        self._asyncSecret = ""
        self._asyncSecretForKeyFile = ""
        self.requestSecret.emit(keyfile)
        waitForSignal(self, self.secretReady)
        if self._asyncSecretForKeyFile == keyfile:
            return self._asyncSecret
        return None

    def requestSecretUi(self, keyfile: str):
        assert onAppThread()
        dlg = showTextInputDialog(
            findParentWidget(self),
            self.tr("Passphrase-protected key file"),
            self.tr("Enter passphrase to use this key file:"),
            subtitleText=escape(compactPath(keyfile)),
            onAccept=lambda secret: self.secretReady.emit(keyfile, secret))
        dlg.rejected.connect(lambda: self.secretReady.emit(keyfile, None))
        lineEdit: QLineEdit = dlg.findChild(QLineEdit)
        lineEdit.setEchoMode(QLineEdit.EchoMode.Password)


class RemoteLinkKeyFileContext:
    def __init__(self, remoteLink: RemoteLink, remote: Remote | str):
        self.remoteLink = remoteLink
        self.remote = remote

    def __enter__(self):
        self.remoteLink.discoverKeyFiles(self.remote)

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.remoteLink.rememberSuccessfulKeyFile()
