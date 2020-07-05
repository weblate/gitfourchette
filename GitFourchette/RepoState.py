import git
import io
import os
import subprocess
import traceback
from PySide2.QtCore import QSettings, QCoreApplication, QMutex, QMutexLocker
from PySide2.QtWidgets import QProgressDialog, QMessageBox
from datetime import datetime
from typing import List, Set
import collections

import settings
from Benchmark import Benchmark
from lanes import LaneGenerator, LaneFrame
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
    mainRefName: str
    laneFrame: LaneFrame
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
        self.mainRefName = None
        self.laneFrame = None
        self.bold = False
        self.hasLocal = True
        self.debugPrefix = None
        self.debugRefreshId = 0


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
    mutex: QMutex
    refCache: collections.defaultdict
    tagCache: collections.defaultdict

    def __init__(self, dir):
        self.dir = os.path.abspath(dir)
        self.repo = git.Repo(dir)
        self.index = self.repo.index
        self.settings = QSettings(self.repo.common_dir + "/fourchette.ini", QSettings.Format.IniFormat)
        self.settings.setValue("GitFourchette", settings.VERSION)
        self.debugRefreshId = 0

        self.commitMetadata = {}

        self.refCache = collections.defaultdict(list)
        self.tagCache = collections.defaultdict(list)
        self.refreshTagAndRefCaches()

        self.boldCommitHash = None

        self.currentRefs = {}

        # QRecursiveMutex causes problems
        self.mutex = QMutex(QMutex.Recursive)

    def refreshTagAndRefCaches(self):
        def _refresh(cache, refList):
            cache.clear()
            for ref in refList:
                try:
                    cache[ref.commit.hexsha].append(ref.name)
                except ValueError as e:
                    print("Error loading tag/ref:", e)
                    # traceback.print_exc()
        _refresh(self.tagCache, self.repo.tags)
        _refresh(self.refCache, self.repo.refs)

    @property
    def shortName(self) -> str:
        return settings.history.getRepoNickname(self.repo.working_tree_dir)

    def mutexLocker(self) -> QMutexLocker:
        return QMutexLocker(self.mutex)

    def getOrCreateMetadata(self, key) -> CommitMetadata:
        assert len(key) == 40, 'metadata key should be 40-byte hex sha'
        if key in self.commitMetadata:
            return self.commitMetadata[key]
        else:
            v = CommitMetadata(key)
            self.commitMetadata[key] = v
            return v

    def getDirtyChanges(self):
        return self.index.diff(None)

    def getUntrackedFiles(self):
        return self.repo.untracked_files

    def getStagedChanges(self):
        return self.index.diff(self.repo.head.commit, R=True)  # R: prevent reversal

    def getOrCreateMetadataFromGitLogOutput(self, commitData):
        hash, parentHashesRaw, author, authorEmail, authorDate, refName, body = commitData.split('\n', 6)

        parentHashes = parentHashesRaw.split()

        wasKnown = hash in self.commitMetadata

        meta = self.getOrCreateMetadata(hash)
        meta.author = author
        meta.authorEmail = authorEmail
        meta.authorTimestamp = int(authorDate)
        meta.body = body
        #meta.body = body[:120]
        #if len(body) > 120:
        #        meta.body += "<snip>"
        meta.parentHashes = parentHashes
        #meta.parentIHashes = [int(h[:7], 16) for h in parentHashes]
        meta.mainRefName = refName

        return meta, wasKnown

    @staticmethod
    def getGitProcess(repo: git.Repo) -> (git.Git.AutoInterrupt, io.TextIOWrapper):
        # Todo: Interesting flags: -z; --log-size

        assert repo.git.GIT_PYTHON_GIT_EXECUTABLE, "GIT_PYTHON_EXECUTABLE wasn't set properly"

        cmd = [
            repo.git.GIT_PYTHON_GIT_EXECUTABLE,
            'log',
            '--all',
            '--pretty=tformat:%H%n%P%n%an%n%ae%n%at%n%S%n%B%n%x00'  # format vs tformat?
        ]

        if settings.prefs.graph_topoOrder:
            cmd.append('--topo-order')

        procWrapper: git.Git.AutoInterrupt = repo.git.execute(cmd, as_process=True)

        proc: subprocess.Popen = procWrapper.proc

        # It's important to NOT fail on encoding errors, because we don't want
        # to stop loading the commit history because of one faulty commit.
        stdoutWrapper = io.TextIOWrapper(proc.stdout, encoding='utf-8', errors='backslashreplace')

        return procWrapper, stdoutWrapper

    def getOrCreateMetadataFromGitStdout(self, stdout: io.TextIOWrapper):
        hash = next(stdout)[:-1]
        wasKnown = hash in self.commitMetadata
        meta = self.getOrCreateMetadata(hash)
        #meta.inthash = int(hash[:7], 16)
        meta.parentHashes = next(stdout)[:-1].split()
        #meta.parentIHashes = [int(h[:7], 16) for h in meta.parentHashes]
        meta.author = next(stdout)[:-1]
        meta.authorEmail = next(stdout)[:-1]
        meta.authorTimestamp = int(next(stdout)[:-1])
        meta.mainRefName = next(stdout)[:-1]

        # Read body, which can be an unlimited number of lines until the \x00 character.
        meta.body = ''
        while True:
            line = next(stdout)
            if line.startswith('\x00'):
                break
            else:
                meta.body += line
        assert '\x00' not in meta.body

        return meta, wasKnown

    def setBoldCommit(self, hexsha: str):
        if self.boldCommitHash and self.boldCommitHash in self.commitMetadata:
            self.commitMetadata[self.boldCommitHash].bold = False
            self.boldCommitHash = None
        self.boldCommitHash = hexsha
        self.getOrCreateMetadata(hexsha).bold = True

    def loadCommitList(self, progress: QProgressDialog):
        procWrapper, stdoutWrapper = self.getGitProcess(self.repo)

        self.setBoldCommit(self.repo.head.commit.hexsha)

        bench = Benchmark("GRAND TOTAL"); bench.__enter__()

        metas = []
        refs = {}
        laneGen = LaneGenerator()
        nextLocal = set()

        i = 0
        while True:
            if i % PROGRESS_INTERVAL == 0:
                progress.setLabelText(F"{i:,} commits processed.")
                QCoreApplication.processEvents()
                if progress.wasCanceled():
                    QMessageBox.warning(progress.parent(),
                        "Loading aborted",
                        F"Loading aborted.\nHistory will be truncated to {i:,} commits.")
                    break
            i += 1

            try:
                meta, wasKnown = self.getOrCreateMetadataFromGitStdout(stdoutWrapper)
            except StopIteration:
                proc: subprocess.Popen = procWrapper.proc
                # Check git log's return code.
                # On Windows, the process seems to take a while to shut down after we catch StopIteration.
                status = proc.poll()
                if status is None:
                    print("Giving some more time for Git to quit...")
                    # This will raise a TimeoutExpired if git is really stuck.
                    status = proc.wait(3)
                assert status is not None, F"git process stopped without a return code?"
                if status != 0:
                    stderrWrapper = io.TextIOWrapper(proc.stderr, errors='backslashreplace')
                    stderr = stderrWrapper.readline().strip()
                    raise git.GitCommandError(procWrapper.args, status, stderr)
                break

            metas.append(meta)

            if meta.mainRefName and meta.mainRefName not in refs:
                refs[meta.mainRefName] = meta.hexsha

            meta.laneFrame = laneGen.step(meta.hexsha, meta.parentHashes)

            self.traceOneCommitAvailability(nextLocal, meta)

        gstatus.setText(F"{self.shortName}: loaded {len(metas):,} commits")

        print(F"Lane: {laneGen.nBytes:,} Bytes - Peak {laneGen.nLanesPeak:,} - Total {laneGen.nLanesTotal:,} - Avg {laneGen.nLanesTotal//len(metas):,} - Vacant {100*laneGen.nLanesVacant/laneGen.nLanesTotal:.2f}%")

        self.order = metas
        self.currentRefs = refs

        bench.__exit__(None, None, None)

        return metas

    @staticmethod
    def traceOneCommitAvailability(nextLocal: set, meta: CommitMetadata):
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

        procWrapper, stdoutWrapper = self.getGitProcess(self.repo)

        wantToSee: set = self.getTaintedCommits()

        self.setBoldCommit(self.repo.head.commit.hexsha)

        if len(wantToSee) == 0:
            gstatus.setText(F"{self.shortName}: no new commits to draw")
            return 0, []

        self.debugRefreshId += 1

        gstatus.setProgressMaximum(5)
        gstatus.setProgressValue(1)

        metas = []
        refs = {}
        lastTainted = None
        nUnknownCommits = 0
        laneGen = LaneGenerator()

        gstatus.setProgressValue(2)

        i = 0
        while True:
            if i % PROGRESS_INTERVAL == 0:
                print("Commits processed:", i)
                QCoreApplication.processEvents()
            i += 1

            try:
                meta, wasKnown = self.getOrCreateMetadataFromGitStdout(stdoutWrapper)
            except StopIteration:
                break
            metas.append(meta)

            if meta.mainRefName and meta.mainRefName not in refs:
                refs[meta.mainRefName] = meta.hexsha

            lastTainted = meta.hexsha

            pLaneFrame = meta.laneFrame
            meta.laneFrame = laneGen.step(meta.hexsha, meta.parentHashes)

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
                    if pLaneFrame != meta.laneFrame:
                        # known commit, but lane data mismatch
                        meta.debugPrefix = "L"  # Lane Mismatch
                        wantToSee.update(meta.parentHashes)
                    else:
                        # stop iterating because there's no more hashes we want to see
                        # TODO: Maybe we should kill git here?
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

    # --- Code graveyard for "sequential" history loading (i.e. call git first, THEN parse its output)
    # We can nuke this when we're done benchmarking
    '''
    def loadCommitList_Sequential(self, progress: QProgressDialog):
        def progressTick(progress: QProgressDialog, i: int):
            progress.setValue(i)
            QCoreApplication.processEvents()
            if progress.wasCanceled():
                print("aborted")
                QMessageBox.warning(progress.parent(), "Loading aborted",
                                    F"Loading aborted.\nHistory will be truncated to {i:,} commits.")
                raise KeyboardInterrupt

        self.setBoldCommit(self.repo.active_branch.commit.hexsha)

        bench = Benchmark("Calling Git")
        bench.__enter__()

        progress.setLabelText("Calling git")
        QCoreApplication.processEvents()
        split, outputBytes = self.getGitOutput(self.repo)
        commitCount = len(split)
        metas = []
        refs = {}

        bench.__exit__(None, None, None)

        with Benchmark("Processing"):
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
        with Benchmark("ComputeLanes " + self.shortName):
            self.computeLanes(metas, lambda i: progressTick(progress, i + commitCount * 2))

        bench.name = "grand total"; bench.__exit__(None, None, None)

        return metas

    @staticmethod
    def getGitOutput(repo: git.Repo) -> List[str]:
        output = repo.git.log(
            topo_order=TOPO_ORDER,
            all=True,
            pretty='tformat:%x00%H%n%P%n%an%n%ae%n%at%n%S%n%B')
        split = output.split('\x00')
        outputBytes = len(output)
        del output
        del split[0]
        split[-1] += '\n'
        return split, outputBytes

    @staticmethod
    def computeLanes(metas, progressTick=None):
        laneGen = LaneGenerator()
        for i, meta in enumerate(metas):
            if progressTick is not None and 0 == i % PROGRESS_INTERVAL:
                progressTick(i)
            # compute lanes
            meta.laneFrame = laneGen.step(meta.hexsha, meta.parentHashes)
        print(F"Lane: {laneGen.nBytes:,} Bytes - Peak {laneGen.nLanesPeak:,} - Total {laneGen.nLanesTotal:,} - Avg {laneGen.nLanesTotal//len(metas):,} - Vacant {100*laneGen.nLanesVacant/laneGen.nLanesTotal:.2f}%")
    '''

    @staticmethod
    def traceCommitAvailability(metas, progressTick=None):
        nextLocal = set()
        for i, meta in enumerate(metas):
            if progressTick is not None and 0 == i % PROGRESS_INTERVAL:
                progressTick(i)
            RepoState.traceOneCommitAvailability(nextLocal, meta)
        assert len(nextLocal) == 0, "there are unreachable commits at the bottom of the graph"

