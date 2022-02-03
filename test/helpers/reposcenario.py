import os
import pygit2
from helpers import testutil


def untrackedEmptyFile(path):
    os.mknod(F"{path}/SomeNewFile.txt")


def nestedUntrackedFiles(path):
    os.mkdir(F"{path}/N")
    os.mknod(F"{path}/N/tata.txt")
    os.mknod(F"{path}/N/toto.txt")
    os.mknod(F"{path}/N/tutu.txt")


def fileWithUnstagedChange(path):
    testutil.writeFile(F"{path}/a/a1.txt", "a1\nPENDING CHANGE\n")


def fileWithStagedAndUnstagedChanges(path):
    repo = pygit2.Repository(path)
    testutil.writeFile(F"{path}/a/a1.txt", "a1\nstaged change\n")
    repo.index.read()
    repo.index.add("a/a1.txt")
    repo.index.write()
    testutil.writeFile(F"{path}/a/a1.txt", "a1\nUNSTAGED CHANGE TO REVERT\nstaged change\n")
    assert repo.status() == {"a/a1.txt": pygit2.GIT_STATUS_INDEX_MODIFIED | pygit2.GIT_STATUS_WT_MODIFIED}


def stagedNewEmptyFile(path):
    repo = pygit2.Repository(path)
    os.mknod(F"{path}/SomeNewFile.txt")
    repo.index.read()
    repo.index.add("SomeNewFile.txt")
    repo.index.write()
    assert repo.status() == {"SomeNewFile.txt": pygit2.GIT_STATUS_INDEX_NEW}


def stashedChange(path):
    repo = pygit2.Repository(path)
    testutil.writeFile(F"{path}/a/a1.txt", "a1\nPENDING CHANGE\n")
    sig = pygit2.Signature("toto", "toto@example.com", 0, 0)
    repo.stash(sig, "helloworld")
    assert repo.status() == {}
