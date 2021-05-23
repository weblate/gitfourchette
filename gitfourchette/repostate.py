from allqt import *
from benchmark import Benchmark
from commitmetadata import CommitMetadata
from collections import defaultdict
from globalstatus import globalstatus
from graph import Graph, GraphSplicer, KF_INTERVAL
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

    graph: Graph

    # Set of head commits for every ref (required to refresh the commit graph)
    currentRefs: set[str]

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

        self.commitSequence = []
        self.commitLookup = {}
        self.graph = None

        self.refsByCommit = defaultdict(list)
        self.refreshRefsByCommitCache()

        self.superproject = self.repo.git.rev_parse("--show-superproject-working-tree")

        self.activeCommitHexsha = None

        self.currentRefs = set()

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
        if meta.batchID >= len(self.batchOffsets):
            print("this should never happen!")
        return self.batchOffsets[meta.batchID] + meta.offsetInBatch

    @staticmethod
    def startGitLogProcess(repo: git.Repo) -> (git.Git.AutoInterrupt, io.TextIOWrapper):
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

    @staticmethod
    def waitForGitProcessToFinish(procWrapper):
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

    def loadCommitList(self, progress: QProgressDialog):
        procWrapper, stdoutWrapper = self.startGitLogProcess(self.repo)

        self.currentRefs = set(ref.commit.hexsha for ref in self.repo.refs)
        self.setBoldCommit(self.repo.head.commit.hexsha)

        bench = Benchmark("GRAND TOTAL"); bench.__enter__()

        commitSequence = []
        # refs = {}
        graph = Graph()
        nextLocal = set()

        i = 0
        while True:
            if i % PROGRESS_INTERVAL == 0:
                if i == 0:
                    progress.setLabelText(F"Waiting for git...")
                else:
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
                self.waitForGitProcessToFinish(procWrapper)
                break

            meta.offsetInBatch = offsetFromTop

            commitSequence.append(meta)

            # if meta.mainRefName and meta.mainRefName not in refs:
            #     refs[meta.mainRefName] = meta.hexsha

            # Fill parent hashes
            for p in meta.parentHashes:
                parentMeta = self.getOrCreateMetadata(p)
                parentMeta.childHashes.insert(0, meta.hexsha)

            self.traceOneCommitAvailability(nextLocal, meta)

        globalstatus.setText(F"{self.shortName}: loaded {len(commitSequence):,} commits")

        progress.setLabelText("Preparing graph...")
        progress.setMaximum(len(commitSequence))
        graphGenerator = graph.startGenerator()
        for meta in commitSequence:
            graphGenerator.createArcsForNewCommit(meta.hexsha, meta.parentHashes)
            if graphGenerator.row % KF_INTERVAL == 0:
                progress.setValue(graphGenerator.row)
                QCoreApplication.processEvents()
                graph.saveKeyframe(graphGenerator)

        self.commitSequence = commitSequence
        self.graph = graph
        self.batchOffsets = [0]
        self.currentBatchID = 0

        bench.__exit__(None, None, None)

        return commitSequence

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

    def loadTaintedCommitsOnly(self):
        globalstatus.setText(F"{self.shortName}: checking for new commits...")

        procWrapper, stdoutWrapper = self.startGitLogProcess(self.repo)

        self.currentBatchID += 1

        globalstatus.setProgressMaximum(5)
        globalstatus.setProgressValue(1)

        newCommitSequence = []

        oldHeads = self.currentRefs
        with Benchmark("Get new heads"):
            newHeads = set(ref.commit.hexsha for ref in self.repo.refs)

        graphSplicer = GraphSplicer(self.graph, oldHeads, newHeads)

        globalstatus.setProgressValue(2)

        i = 0
        while graphSplicer.keepGoing:
            if i % PROGRESS_INTERVAL == 0:
                print("Commits processed:", i)
                QCoreApplication.processEvents()
            offsetFromTop = i
            i += 1

            try:
                meta, wasKnown = self.getOrCreateMetadataFromGitStdout(stdoutWrapper)
            except StopIteration:
                self.waitForGitProcessToFinish(procWrapper)
                break
            newCommitSequence.append(meta)

            graphSplicer.spliceNewCommit(meta.hexsha, meta.parentHashes, wasKnown)

            meta.offsetInBatch = offsetFromTop
            meta.batchID = self.currentBatchID

            meta.debugPrefix = "R" if wasKnown else "N"  # Redrawn or New

            # Fill parent hashes
            for p in meta.parentHashes:
                parentMeta = self.getOrCreateMetadata(p)
                parentMeta.childHashes.insert(0, meta.hexsha)

        graphSplicer.finish()

        globalstatus.setProgressValue(3)

        with Benchmark("Nuke unreachable commits from cache"):
            for trashedCommit in (graphSplicer.oldCommitsSeen - graphSplicer.newCommitsSeen):
                del self.commitLookup[trashedCommit]

        # Piece correct commit sequence back together
        self.commitSequence = newCommitSequence[:graphSplicer.equilibriumNewRow] + self.commitSequence[graphSplicer.equilibriumOldRow:]
        self.currentRefs = newHeads

        # Compute new batch offset
        assert self.currentBatchID == len(self.batchOffsets)
        self.batchOffsets = [previousOffset + graphSplicer.oldGraphRowOffset for previousOffset in self.batchOffsets]
        self.batchOffsets.append(0)

        # todo: this will do a pass on all commits. Can we look at fewer commits?
        self.traceCommitAvailability(self.commitSequence)

        globalstatus.setProgressValue(4)

        self.setBoldCommit(self.repo.head.commit.hexsha)

        return graphSplicer.equilibriumOldRow, graphSplicer.equilibriumNewRow

    """
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
    """

    @staticmethod
    def traceCommitAvailability(metas, progressTick=None):
        nextLocal = set()
        for i, meta in enumerate(metas):
            if progressTick is not None and 0 == i % PROGRESS_INTERVAL:
                progressTick(i)
            RepoState.traceOneCommitAvailability(nextLocal, meta)
        assert len(nextLocal) == 0, "there are unreachable commits at the bottom of the graph"

