import git
import os
import traceback
from PySide2.QtCore import QSettings, QCoreApplication
from PySide2.QtWidgets import QProgressDialog
from datetime import datetime

import settings
from Lanes import Lanes


class CommitMetadata:
    # Immutable attributes
    hexsha: str
    author: str
    authorEmail: str
    authorTimestamp: int
    body: str

    # Attributes that may change as the repository evolves
    tags: []
    refs: []
    lane: int
    laneData: []
    bold: bool
    hasLocal: bool

    def __init__(self, hexsha: str):
        self.hexsha = hexsha
        self.author = ""
        self.authorEmail = ""
        self.authorTimestamp = 0
        self.body = ""
        self.tags = []
        self.refs = []
        self.lane = 0
        self.laneData = None
        self.bold = False
        self.hasLocal = False

    def commit(self, repo: git.Repo):
        return repo.commit(self.hexsha)


class RepoState:
    dir: str
    repo: git.Repo
    index: git.IndexFile
    settings: QSettings
    commitMetadata: dict
    currentCommitAtRef: dict

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
        for ref in self.repo.refs:
            try:
                self.getOrCreateMetadata(ref.commit.hexsha).refs.append(ref.name)
            except BaseException as e:
                print("Error loading ref")
                traceback.print_exc()

        self.currentCommitAtRef = {}

        """
        for remote in self.repo.remotes:
            for ref in remote.refs:
                self.getOrCreateMetadata(ref.commit.hexsha).refs.append(F"{ref.remote_name}/{ref.remote_head}")
        """

    def getOrCreateMetadata(self, key) -> CommitMetadata:
        if key in self.commitMetadata:
            return self.commitMetadata[key]
        else:
            v = CommitMetadata(key)
            self.commitMetadata[key] = v
            return v

    def loadCommitList(self, progress: QProgressDialog, progressTick):
        repo: git.Repo = self.repo

        boldCommitHash = repo.active_branch.commit.hexsha
        self.getOrCreateMetadata(boldCommitHash).bold = True

        progress.setLabelText("Git.")
        QCoreApplication.processEvents()
        timeA = datetime.now()
        output = repo.git.log(topo_order=True, all=True, pretty='tformat:%x00%H%n%P%n%an%n%ae%n%at%n%S%n%B')

        timeB = datetime.now()

        progress.setLabelText("Split.")
        QCoreApplication.processEvents()
        split = output.split('\x00')
        del split[0]
        split[-1] += '\n'
        commitCount = len(split)

        progress.setLabelText(F"Processing {commitCount:,} commits ({len(output)//1024:,} KB).")
        progress.setMaximum(4 * commitCount)

        metas = []

        refs = {}

        for i, commitData in enumerate(split):
            progressTick(progress, i + commitCount * 0)

            hash, parentHashesRaw, author, authorEmail, authorDate, refName, body = commitData.split('\n', 6)

            parentHashes = parentHashesRaw.split()

            if refName and refName not in refs:
                refs[refName] = hash

            meta = self.getOrCreateMetadata(hash)
            meta.author = author
            meta.authorEmail = authorEmail
            meta.authorTimestamp = int(authorDate)
            meta.body = body
            meta.parentHashes = parentHashes
            meta.mainRefName = refName
            metas.append(meta)

        self.currentCommitAtRef = refs

        progress.setLabelText(F"Tracing commit availability.")
        nextLocal = set()
        for i, meta in enumerate(metas):
            progressTick(progress, i + commitCount * 1)
            if meta.hexsha in nextLocal:
                meta.hasLocal = True
                nextLocal.remove(meta.hexsha)
            elif meta.mainRefName == "HEAD" or meta.mainRefName.startswith("refs/heads/"):
                meta.hasLocal = True
            else:
                meta.hasLocal = False
            if meta.hasLocal:
                for p in meta.parentHashes:
                    nextLocal.add(p)
        assert(len(nextLocal) == 0)

        laneGen = Lanes()
        progress.setLabelText(F"Drawing graph.")
        for i, meta in enumerate(metas):
            progressTick(progress, i + commitCount * 2)
            # compute lanes
            meta.lane, meta.laneData = laneGen.step(meta.hexsha, meta.parentHashes)

        timeC = datetime.now()

        print(int((timeC - timeB).total_seconds() * 1000), int((timeB - timeA).total_seconds() * 1000))
        print(refs)

        '''
        QCoreApplication.processEvents()
        import pickle
        with open(F'/tmp/gitfourchette-{settings.history.getRepoNickname(repo.working_tree_dir)}.pickle', 'wb') as handle:
            pickle.dump(self.repoWidget.state.commitMetadata, handle, protocol=pickle.HIGHEST_PROTOCOL)
        '''

        return metas
