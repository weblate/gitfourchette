import git
import os
import traceback
from PySide2.QtCore import QSettings
import settings


class CommitMetadata:
    hexsha: str
    author: str
    authorEmail: str
    authorTimestamp: int
    body: str
    tags: []
    refs: []
    lane: int
    laneData: []
    bold: bool

    def __init__(self, hexsha: str):
        self.hexsha = hexsha
        self.author = ""
        self.authorEmail = ""
        self.authorTimestamp = 0
        self.body = ""
        self.tags = []
        self.refs = []
        self.lane = -1
        self.laneData = []
        self.bold = False

    def commit(self, repo: git.Repo):
        return repo.commit(self.hexsha)


class RepoState:
    dir: str
    repo: git.Repo
    index: git.IndexFile
    settings: QSettings
    commitMetadata: dict

    def __init__(self, dir):
        self.dir = os.path.abspath(dir)
        self.repo = git.Repo(dir)
        self.index = self.repo.index
        self.settings = QSettings(self.repo.common_dir + "/fourchette.ini", QSettings.Format.IniFormat)
        self.settings.setValue("GitFourchette", settings.VERSION)

        self.commitMetadata = {}
        for tag in self.repo.tags:
            try:
                self.getOrCreateMetadata(tag.commit.hexsha).tags.append(tag.name)
            except BaseException as e:  # the linux repository has 2 tags pointing to trees instead of commits
                print("Error loading tag")
                traceback.print_exc()
        for remote in self.repo.remotes:
            for ref in remote.refs:
                self.getOrCreateMetadata(ref.commit.hexsha).refs.append(F"{ref.remote_name}/{ref.remote_head}")

    def getOrCreateMetadata(self, key) -> CommitMetadata:
        if key in self.commitMetadata:
            return self.commitMetadata[key]
        else:
            v = CommitMetadata(key)
            self.commitMetadata[key] = v
            return v

