"""
Manage proprietary settings in a repository's .git/config and .git/gitfourchette.json.
"""

from dataclasses import dataclass, field

from gitfourchette.appconsts import *
from gitfourchette.forms.signatureform import SignatureOverride
from gitfourchette.porcelain import *
from gitfourchette.prefsfile import PrefsFile

KEY_PREFIX = "gitfourchette-"


class RefSort(enum.IntEnum):
    TimeDesc = 0
    TimeAsc = 1
    AlphaAsc = 2
    AlphaDesc = 3
    Default = TimeDesc


@dataclass
class RepoPrefs(PrefsFile):
    _filename = f"{APP_SYSTEM_NAME}.json"
    _allowMakeDirs = False
    _parentDir = ""

    _repo: Repo
    draftCommitMessage: str = ""
    draftCommitSignature: Signature | None = None
    draftCommitSignatureOverride: SignatureOverride = SignatureOverride.Nothing
    draftAmendMessage: str = ""
    hiddenRefPatterns: set = field(default_factory=set)
    collapseCache: set = field(default_factory=set)
    sortBranches: RefSort = RefSort.Default
    sortRemoteBranches: RefSort = RefSort.Default
    sortTags: RefSort = RefSort.Default

    def getParentDir(self):
        return self._parentDir

    def clearDraftCommit(self):
        self.draftCommitMessage = ""
        self.draftCommitSignature = None
        self.draftCommitSignatureOverride = SignatureOverride.Nothing
        self.setDirty()

    def clearDraftAmend(self):
        self.draftAmendMessage = ""
        self.setDirty()

    def getRemoteKeyFile(self, remote: str) -> str:
        return RepoPrefs.getRemoteKeyFileForRepo(self._repo, remote)

    def setRemoteKeyFile(self, remote: str, path: str):
        RepoPrefs.setRemoteKeyFileForRepo(self._repo, remote, path)

    @staticmethod
    def getRemoteKeyFileForRepo(repo: Repo, remote: str):
        return repo.get_config_value(("remote", remote, KEY_PREFIX+"keyfile"))

    @staticmethod
    def setRemoteKeyFileForRepo(repo: Repo, remote: str, path: str):
        repo.set_config_value(("remote", remote, KEY_PREFIX+"keyfile"),  path)
