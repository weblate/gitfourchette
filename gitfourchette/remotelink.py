import os.path

import util
from allqt import QStandardPaths, QObject, Signal
import pygit2


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


class RemoteLinkSignals(QObject):
    message = Signal(str)
    progress = Signal(int, int, int)


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
                    print("[RemoteLink] Discovered key pair", privkey)
                    self.keypairFiles.append((pubkey, privkey))

        self.signals.message.connect(lambda m: print("[RemoteLink] " + m))

    def sideband_progress(self, string):
        self.signals.message.emit("Sideband progress: " + string)

    # def certificate_check(self, certificate, valid, host):
    #     print("[RemoteCallbacks] Certificate Check", certificate, valid, host)
    #     return 1

    def credentials(self, url, username_from_url, allowed_types):
        self.attempts += 1

        if self.attempts > 10:
            raise ConnectionRefusedError("Too many credential retries.")

        allowedTypeNames = []
        for k, v in AUTH_NAMES.items():
            if allowed_types & k:
                allowedTypeNames.append(v)
        print("Auths accepted by server: " + ", ".join(allowedTypeNames))

        if self.keypairFiles and (allowed_types & pygit2.credentials.GIT_CREDENTIAL_SSH_KEY):
            pubkey, privkey = self.keypairFiles.pop()
            self.signals.message.emit(F"Attempting login...\n{util.compactSystemPath(pubkey)}")
            return pygit2.Keypair(username_from_url, pubkey, privkey, "")
            # return pygit2.KeypairFromAgent(username_from_url)
        else:
            raise NotImplementedError("Unsupported credentials")

    def transfer_progress(self, stats: pygit2.remote.TransferProgress):
        obj = min(stats.indexed_objects, stats.total_objects)
        self.signals.message.emit(F"{obj} of {stats.total_objects} objects ready\n{stats.received_bytes//1024:,} KB")
        self.signals.progress.emit(0, stats.total_objects, obj)
        # TODO: check that returning non-0 here can be used to cancel (https://libgit2.org/libgit2/#HEAD/group/callback/git_indexer_progress_cb)

    def update_tips(self, refname, old, new):
        self.signals.message.emit(F"Update tips {refname} {old} {new}")

    def push_update_reference(self, refname, message):
        self.signals.message.emit(F"Push update ref {refname} {message}")
