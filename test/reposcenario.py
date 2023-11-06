from .util import *
from gitfourchette.porcelain import RepositoryContext
import os
import pygit2


def fileWithStagedAndUnstagedChanges(path):
    with RepositoryContext(path) as repo:
        writeFile(F"{path}/a/a1.txt", "a1\nstaged change\n")
        repo.index.read()
        repo.index.add("a/a1.txt")
        repo.index.write()
        writeFile(F"{path}/a/a1.txt", "a1\nUNSTAGED CHANGE TO REVERT\nstaged change\n")
        assert repo.status() == {"a/a1.txt": pygit2.GIT_STATUS_INDEX_MODIFIED | pygit2.GIT_STATUS_WT_MODIFIED}


def stagedNewEmptyFile(path):
    with RepositoryContext(path) as repo:
        writeFile(F"{path}/SomeNewFile.txt", "")
        repo.index.read()
        repo.index.add("SomeNewFile.txt")
        repo.index.write()
        assert repo.status() == {"SomeNewFile.txt": pygit2.GIT_STATUS_INDEX_NEW}


def stashedChange(path):
    with RepositoryContext(path) as repo:
        writeFile(F"{path}/a/a1.txt", "a1\nPENDING CHANGE\n")
        sig = pygit2.Signature("toto", "toto@example.com", 0, 0)
        repo.stash(sig, "helloworld")
        assert repo.status() == {}

