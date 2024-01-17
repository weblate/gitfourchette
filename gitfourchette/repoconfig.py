"""
Manage proprietary settings in a repository's .git/config.
"""

from contextlib import suppress
from gitfourchette.porcelain import *


KEY_PREFIX = "gitfourchette-"


def getRemoteKeyFile(repo: Repo, remote: str) -> str:
    return repo.get_config_value(("remote", remote, KEY_PREFIX+"keyfile"))


def setRemoteKeyFile(repo: Repo, remote: str, path: str):
    repo.set_config_value(("remote", remote, KEY_PREFIX+"keyfile"),  path)
