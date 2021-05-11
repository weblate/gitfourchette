from allqt import *
from benchmark import Benchmark
from commitmetadata import CommitMetadata
from collections import defaultdict
from globalstatus import globalstatus
from graphgenerator import GraphGenerator
import git
import io
import os
import settings
import subprocess


PROGRESS_INTERVAL = 5000


# For debugging
class Dump:
    pass


class RepoState:
    dir: str
    repo: git.Repo
    index: git.IndexFile
    settings: QSettings

    # ordered list of commits
    commitSequence: list[CommitMetadata]

    # commit hexsha --> cached commit metadata
    # (values are shared with commitSequence)
    commitLookup: dict[str, CommitMetadata]

    # ref name --> commit hexsha at tip of ref
    currentRefs: dict[str, str]

    # path of superproject if this is a submodule
    superproject: str

    # hash of the active commit (to make it bold)
    activeCommitHexsha: str

    # Everytime we refresh, new rows may be inserted at the top of the graph.
    # This may push existing rows down, away from the top of the graph.
    # To avoid recomputing offsetFromTop for every commit metadata,
    # we keep track of the general offset of every batch of rows created by every refresh.
    batchOffsets: list[int]

    currentBatchID: int

    mutex: QMutex

    # commit hexsha --> list of (refName, isTag flag)
    refsByCommit: defaultdict[str, list[tuple[str, bool]]]

    def __init__(self, dir):
        self.dir = os.path.abspath(dir)
        self.repo = git.Repo(dir)
        self.index = self.repo.index
        self.settings = QSettings(self.repo.common_dir + "/fourchette.ini", QSettings.Format.IniFormat)
        self.settings.setValue("GitFourchette", settings.VERSION)
        self.currentBatchID = 0

        self.commitLookup = {}

        self.refsByCommit = defaultdict(list)
        self.refreshRefsByCommitCache()

        self.superproject = self.repo.git.rev_parse("--show-superproject-working-tree")

        self.activeCommitHexsha = None

        self.currentRefs = {}

        self.mutex = QMutex()

    def refreshRefsByCommitCache(self):
        self.refsByCommit.clear()
        ref: git.Reference
        for ref in self.repo.refs:
            isTag = hasattr(ref, 'tag')
            self.refsByCommit[ref.object.hexsha].append( (ref.name, isTag) )

    @property
    def shortName(self) -> str:
        prefix = ""
        if self.superproject:
            superprojectNickname = settings.history.getRepoNickname(self.superproject)
            prefix = superprojectNickname + ": "

        return prefix + settings.history.getRepoNickname(self.repo.working_tree_dir)

    def mutexLocker(self) -> QMutexLocker:
        return QMutexLocker(self.mutex)

    def getOrCreateMetadata(self, hexsha) -> CommitMetadata:
        assert len(hexsha) == 40, 'metadata key should be 40-byte hexsha'
        if hexsha in self.commitLookup:
            return self.commitLookup[hexsha]
        else:
            # We don't know anything about this commit yet except for its hash.
            # Create a metadata object for it now so we can start referring to the object.
            # The details about the commit will be filled in later.
            v = CommitMetadata(hexsha)
            v.childHashes = []  # MUST initialize this
            self.commitLookup[hexsha] = v
            return v

    def getDirtyChanges(self) -> git.DiffIndex:
        return self.index.diff(None)

    def getUntrackedFiles(self) -> list[str]:
        return self.repo.untracked_files

    def getStagedChanges(self) -> git.DiffIndex:
        return self.index.diff(self.repo.head.commit, R=True)  # R: prevent reversal

    def getCommitSequentialIndex(self, hexsha: str):
        meta = self.commitLookup[hexsha]
        return self.batchOffsets[meta.batchID] + meta.offsetInBatch

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
        wasKnown = hash in self.commitLookup
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
        if self.activeCommitHexsha and (self.activeCommitHexsha in self.commitLookup):
            self.commitLookup[self.activeCommitHexsha].bold = False
            self.activeCommitHexsha = None
        self.activeCommitHexsha = hexsha
        self.getOrCreateMetadata(hexsha).bold = True

    def loadCommitList(self, progress: QProgressDialog):
        procWrapper, stdoutWrapper = self.getGitProcess(self.repo)

        self.setBoldCommit(self.repo.head.commit.hexsha)

        bench = Benchmark("GRAND TOTAL"); bench.__enter__()

        metas = []
        refs = {}
        graphGen = GraphGenerator()
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
            offsetFromTop = i
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

            meta.offsetInBatch = offsetFromTop

            metas.append(meta)

            if meta.mainRefName and meta.mainRefName not in refs:
                refs[meta.mainRefName] = meta.hexsha

            meta.graphFrame = graphGen.step(meta.hexsha, meta.parentHashes)

            # Fill parent hashes
            for p in meta.parentHashes:
                parentMeta = self.getOrCreateMetadata(p)
                parentMeta.childHashes.insert(0, meta.hexsha)

            self.traceOneCommitAvailability(nextLocal, meta)

        globalstatus.setText(F"{self.shortName}: loaded {len(metas):,} commits")

        print(F"Graph Frames: {graphGen.nBytes//1024:,} KB - "
              F"Peak Lanes: {graphGen.nLanesPeak:,} - "
              F"Total Lanes: {graphGen.nLanesTotal:,} - "
              F"Avg Lanes: {graphGen.nLanesTotal//len(metas):,} - "
              F"Lane Vacancy: {100*graphGen.nLanesVacant/graphGen.nLanesTotal:.2f}%")

        self.commitSequence = metas
        self.batchOffsets = [0]
        self.currentRefs = refs
        self.currentBatchID = 0

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

    def getTaintedCommits(self) -> set[str]:
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
        globalstatus.setText(F"{self.shortName}: checking for new commits...")

        procWrapper, stdoutWrapper = self.getGitProcess(self.repo)

        wantToSee: set = self.getTaintedCommits()

        self.setBoldCommit(self.repo.head.commit.hexsha)

        if len(wantToSee) == 0:
            globalstatus.setText(F"{self.shortName}: no new commits to draw")
            return 0, []

        self.currentBatchID += 1

        globalstatus.setProgressMaximum(5)
        globalstatus.setProgressValue(1)

        metas = []
        refreshedHashes = set()
        refs = {}
        lastTainted = None
        nUnknownCommits = 0
        graphGen = GraphGenerator()

        globalstatus.setProgressValue(2)

        i = 0
        while True:
            if i % PROGRESS_INTERVAL == 0:
                print("Commits processed:", i)
                QCoreApplication.processEvents()
            offsetFromTop = i
            i += 1

            try:
                meta, wasKnown = self.getOrCreateMetadataFromGitStdout(stdoutWrapper)
            except StopIteration:
                break
            metas.append(meta)
            refreshedHashes.add(meta.hexsha)

            if meta.mainRefName and meta.mainRefName not in refs:
                refs[meta.mainRefName] = meta.hexsha

            lastTainted = meta.hexsha

            prevGraphFrame = meta.graphFrame
            meta.graphFrame = graphGen.step(meta.hexsha, meta.parentHashes)

            meta.offsetInBatch = offsetFromTop
            meta.batchID = self.currentBatchID
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
                    if prevGraphFrame != meta.graphFrame:
                        # known commit, but lane data mismatch
                        meta.debugPrefix = "L"  # Lane Mismatch
                        wantToSee.update(meta.parentHashes)
                    else:
                        # stop iterating because there's no more hashes we want to see
                        # TODO: Maybe we should kill git here?
                        break

            # Fill parent hashes
            for p in meta.parentHashes:
                parentMeta = self.getOrCreateMetadata(p)
                parentMeta.childHashes.insert(0, meta.hexsha)

        globalstatus.setProgressValue(3)

        print(F"last tainted hash: {lastTainted}")

        nAddedAtTop = len(metas)
        nRemovedAtTop = 1

        # Nuke references to tainted commits,
        # and find out how many tainted commits to trim at the front of the sequence.
        for oldCommit in self.commitSequence:
            if oldCommit.hexsha == lastTainted:
                # Last tainted commit -- all following commits are clean, stop here
                break

            nRemovedAtTop += 1

            # Remove tainted commit from parents' children
            for parentHash in oldCommit.parentHashes:
               if parentHash in self.commitLookup:
                   self.commitLookup[parentHash].childHashes.remove(oldCommit.hexsha)

            # If the commit hash is now unreachable, nuke it from lookup dict to avoid a leak
            if oldCommit.hexsha not in refreshedHashes:
                del self.commitLookup[oldCommit.hexsha]

        # Piece correct commit sequence back together
        self.commitSequence = metas + self.commitSequence[nRemovedAtTop:]

        # Compute new batch offset
        assert self.currentBatchID == len(self.batchOffsets)
        self.batchOffsets = [previousOffset + nAddedAtTop - nRemovedAtTop for previousOffset in self.batchOffsets]
        self.batchOffsets.append(0)

        globalstatus.setText(F"{self.shortName}: loaded {nUnknownCommits:,} new commits; redrew {len(metas):,} rows; last tainted hash {lastTainted[:7]}")

        # todo: this will do a pass on all commits. Can we look at fewer commits?
        self.traceCommitAvailability(self.commitSequence)

        self.currentRefs = refs

        globalstatus.setProgressValue(4)

        return nRemovedAtTop, metas

    # For debugging
    def loadCommitDump(self, dump: Dump):
        self.commitLookup = dump.data
        self.commitSequence = [self.commitLookup[k] for k in dump.order]
        self.currentRefs = dump.currentRefs
        return self.commitSequence

    # For debugging
    def makeCommitDump(self) -> Dump:
        dump = Dump()
        dump.data = self.commitLookup
        dump.order = [c.hexsha for c in self.commitSequence]
        dump.currentRefs = self.currentRefs
        return dump

    @staticmethod
    def traceCommitAvailability(metas, progressTick=None):
        nextLocal = set()
        for i, meta in enumerate(metas):
            if progressTick is not None and 0 == i % PROGRESS_INTERVAL:
                progressTick(i)
            RepoState.traceOneCommitAvailability(nextLocal, meta)
        assert len(nextLocal) == 0, "there are unreachable commits at the bottom of the graph"

