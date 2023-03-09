"""
Manage proprietary settings in a repository's .git/config.
"""

import contextlib
import pygit2


KEY_PREFIX = "gitfourchette-"


def getRemoteKeyFile(repo: pygit2.Repository, remote: str):
    try:
        return repo.config[f"remote.{remote}.{KEY_PREFIX}keyfile"]
    except KeyError:
        return ""


def setRemoteKeyFile(repo: pygit2.Repository, remote: str, path: str):
    configKey = f"remote.{remote}.{KEY_PREFIX}keyfile"

    if path:
        repo.config[configKey] = path
    else:
        with contextlib.suppress(KeyError):
            del repo.config[configKey]
