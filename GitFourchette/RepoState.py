import git
import os
import traceback
from PySide2.QtCore import QSettings, QCoreApplication
from PySide2.QtWidgets import QProgressDialog
from datetime import datetime
from typing import List, Set

import settings
from Lanes import Lanes
from status import gstatus


PROGRESS_INTERVAL = 5000


class Dump:
    pass


class CommitMetadata:
    # Immutable attributes
    hexsha: str
    author: str
    authorEmail: str
    authorTimestamp: int
    body: str
    parentHashes: List[str]

    # Attributes that may change as the repository evolves
    tags: List[str]
    refs: List[str]
    mainRefName: str
    lane: int
    laneData: List[int]
    bold: bool
    hasLocal: bool
    debugPrefix: str
    debugRefreshId: int

    def __init__(self, hexsha: str):
        self.hexsha = hexsha
        self.author = ""
        self.authorEmail = ""
        self.authorTimestamp = 0
        self.body = ""
        self.parentHashes = []
        self.debugPrefix = None
        self.tags = []
        self.refs = []
        self.mainRefName = None
        self.lane = 0
        self.laneData = None
        self.bold = False
        self.hasLocal = True
        self.debugPrefix = None
        self.debugRefreshId = 0

    def commit(self, repo: git.Repo):
        return repo.commit(self.hexsha)


class RepoState:
    dir: str
    repo: git.Repo
    index: git.IndexFile
    settings: QSettings
    commitMetadata: dict
    currentRefs: dict
    boldCommitHash: str
    order: List[CommitMetadata]
    debugRefreshId: int

    def __init__(self, dir):
        self.dir = os.path.abspath(dir)
        self.repo = git.Repo(dir)
        self.index = self.repo.index
        self.settings = QSettings(self.repo.common_dir + "/fourchette.ini", QSettings.Format.IniFormat)
        self.settings.setValue("GitFourchette", settings.VERSION)
        self.debugRefreshId = 0

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

        self.boldCommitHash = None

        self.currentRefs = {}

        """
        for remote in self.repo.remotes:
            for ref in remote.refs:
                self.getOrCreateMetadata(ref.commit.hexsha).refs.append(F"{ref.remote_name}/{ref.remote_head}")
        """

    @property
    def shortName(self) -> str:
        return settings.history.getRepoNickname(self.repo.working_tree_dir)

    def getOrCreateMetadata(self, key) -> CommitMetadata:
        if key in self.commitMetadata:
            return self.commitMetadata[key]
        else:
            v = CommitMetadata(key)
            self.commitMetadata[key] = v
            return v

    def getOrCreateMetadataFromGitLogOutput(self, commitData):
        hash, parentHashesRaw, author, authorEmail, authorDate, refName, body = commitData.split('\n', 6)

        parentHashes = parentHashesRaw.split()

        wasKnown = hash in self.commitMetadata

        meta = self.getOrCreateMetadata(hash)
        meta.author = author
        meta.authorEmail = authorEmail
        meta.authorTimestamp = int(authorDate)
        meta.body = body
        meta.parentHashes = parentHashes
        meta.mainRefName = refName

        return meta, wasKnown

    def setBoldCommit(self, hexsha: str):
        if self.boldCommitHash and self.boldCommitHash in self.commitMetadata:
            self.commitMetadata[self.boldCommitHash].bold = False
            self.boldCommitHash = None
        self.boldCommitHash = hexsha
        self.getOrCreateMetadata(hexsha).bold = True

    def loadCommitList(self, progress: QProgressDialog, progressTick):
        self.setBoldCommit(self.repo.active_branch.commit.hexsha)

        progress.setLabelText("Calling git")
        QCoreApplication.processEvents()
        split, outputBytes = self.getGitOutput(self.repo)
        commitCount = len(split)
        metas = []
        refs = {}

        progress.setLabelText(F"Processing {commitCount:,} commits ({outputBytes//1024:,} KB)")
        progress.setMaximum(3 * commitCount + 1)

        for i, commitData in enumerate(split):
            if 0 == i % PROGRESS_INTERVAL:
                progressTick(progress, i + commitCount * 0)

            meta, wasKnown = self.getOrCreateMetadataFromGitLogOutput(commitData)
            metas.append(meta)

            if meta.mainRefName and meta.mainRefName not in refs:
                refs[meta.mainRefName] = meta.hexsha

        gstatus.setText(F"{self.shortName}: loaded {len(metas):,} commits")

        self.order = metas
        self.currentRefs = refs

        progress.setLabelText("Tracing commit availability")
        QCoreApplication.processEvents()
        self.traceCommitAvailability(metas, lambda i: progressTick(progress, i + commitCount * 1))

        progress.setLabelText("Computing lanes")
        QCoreApplication.processEvents()
        self.computeLanes(metas, lambda i: progressTick(progress, i + commitCount * 2))

        return metas

    @staticmethod
    def getGitOutput(repo: git.Repo) -> List[str]:
        output = repo.git.log(topo_order=True, all=True, pretty='tformat:%x00%H%n%P%n%an%n%ae%n%at%n%S%n%B')
        split = output.split('\x00')
        outputBytes = len(output)
        del output
        del split[0]
        split[-1] += '\n'
        return split, outputBytes

    @staticmethod
    def traceCommitAvailability(metas, progressTick=None):
        nextLocal = set()
        for i, meta in enumerate(metas):
            if progressTick is not None and 0 == i % PROGRESS_INTERVAL:
                progressTick(i)
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

    @staticmethod
    def computeLanes(metas, progressTick=None):
        laneGen = Lanes()
        for i, meta in enumerate(metas):
            if progressTick is not None and 0 == i % PROGRESS_INTERVAL:
                progressTick(i)
            # compute lanes
            meta.lane, meta.pLaneData, meta.laneData = laneGen.step(meta.hexsha, meta.parentHashes)

    def getTaintedCommits(self) -> Set[str]:
        repo = self.repo

        tainted = set()
        clean = set()

        #TODO: some commits are pointed to by several refs... but the %S flag in git log only gives us one commit at a time! maybe we should use %d instead?
        for k in self.currentRefs:
            #print(F"current state: ref {k} --> {self.currentRefs[k]}")
            pass
        for ref in repo.refs:
            try:
                previous = self.currentRefs[ref.path]
            except KeyError:
                #print("skipped......:", ref.path)
                continue
                previous = None
            hash = ref.commit.hexsha
            if previous != hash:
                #print("tainted......:", ref.path, "\t", previous, "---->", hash)
                tainted.add(hash)
            else:
                #print("clean........:", ref.path, "\t", previous)
                clean.add(hash)

        tainted -= clean

        print("tainted:", tainted)
        return tainted

    def loadTaintedCommitsOnly(self):
        gstatus.setText(F"{self.shortName}: checking for new commits...")
        self.setBoldCommit(self.repo.active_branch.commit.hexsha)
        wantToSee: set = self.getTaintedCommits()

        if len(wantToSee) == 0:
            gstatus.setText(F"{self.shortName}: no new commits to draw")
            return 0, []

        self.debugRefreshId += 1

        gstatus.setProgressMaximum(5)
        gstatus.setProgressValue(1)

        split, _ = self.getGitOutput(self.repo)
        metas = []
        refs = {}
        lastTainted = None
        nUnknownCommits = 0
        laneGen = Lanes()

        gstatus.setProgressValue(2)

        for i, commitData in enumerate(split):
            # progressTick(progress, i + commitCount * 0)
            if i % 10000 == 0:
                QCoreApplication.processEvents()

            meta, wasKnown = self.getOrCreateMetadataFromGitLogOutput(commitData)
            metas.append(meta)

            if meta.mainRefName and meta.mainRefName not in refs:
                refs[meta.mainRefName] = meta.hexsha

            lastTainted = meta.hexsha

            pLane, pLaneData = meta.lane, meta.laneData
            meta.lane, meta.laneData = laneGen.step(meta.hexsha, meta.parentHashes)

            meta.debugRefreshId = self.debugRefreshId
            meta.debugPrefix = "R"  # Redrawn
            meta.red = True

            if not wasKnown:
                nUnknownCommits += 1
                meta.debugPrefix = "N"  # New
                wantToSee.update(meta.parentHashes)

            if meta.hexsha in wantToSee:
                wantToSee.remove(meta.hexsha)
                if len(wantToSee) == 0:
                    #assert wasKnown #<-- assertion incorrect if the entire repository changes
                    if meta.lane != pLane or meta.laneData != pLaneData:
                        # known commit, but lane data mismatch
                        meta.debugPrefix = "L"  # Lane Mismatch
                        wantToSee.update(meta.parentHashes)
                    else:
                        # stop iterating because there's no more hashes we want to see
                        break

        gstatus.setProgressValue(3)

        print(F"last tainted hash: {lastTainted}")

        for lastTaintedIndex, v in enumerate(self.order):
            if v.hexsha == lastTainted:
                break

        self.order = metas + self.order[lastTaintedIndex+1:]
        print(F"new order: {len(self.order)}")

        gstatus.setText(F"{self.shortName}: loaded {nUnknownCommits:,} new commits; redrew {len(metas):,} rows; last tainted hash {lastTainted[:7]}")

        # todo: this will do a pass on all commits. Can we look at fewer commits?
        self.traceCommitAvailability(self.order)
        # Recompute lanes only on redrawn commits
        self.computeLanes(metas)
        self.currentRefs = refs

        gstatus.setProgressValue(4)

        return lastTaintedIndex+1, metas

    def loadCommitDump(self, dump: Dump):
        self.commitMetadata = dump.data
        self.order = [self.commitMetadata[k] for k in dump.order]
        self.currentRefs = dump.currentRefs
        return self.order

    def makeCommitDump(self) -> Dump:
        dump = Dump()
        dump.data = self.commitMetadata
        dump.order = [c.hexsha for c in self.order]
        dump.currentRefs = self.currentRefs
        return dump
