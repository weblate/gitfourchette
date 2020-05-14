import git
import os
import traceback
from PySide2.QtCore import QSettings
import settings


class CommitMetadata:
    commit: git.Commit
    tags: []
    refs: []

    def __init__(self, commit: git.Commit):
        self.commit = commit
        self.tags = []
        self.refs = []


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
                self.getOrCreateMetadata(tag.commit).tags.append(tag.name)
            except BaseException as e:  # the linux repository has 2 tags pointing to trees instead of commits
                print("Error loading tag")
                traceback.print_exc()
        for remote in self.repo.remotes:
            for ref in remote.refs:
                self.getOrCreateMetadata(ref.commit).refs.append(F"{ref.remote_name}/{ref.remote_head}")

    def getOrCreateMetadata(self, commit) -> CommitMetadata:
        key = commit.binsha
        if key in self.commitMetadata:
            return self.commitMetadata[key]
        else:
            v = CommitMetadata(commit)
            self.commitMetadata[key] = v
            return v

