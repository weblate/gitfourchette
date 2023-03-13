from collections import defaultdict
from dataclasses import dataclass, field
from gitfourchette import log
from gitfourchette import porcelain, tempdir
from gitfourchette import settings
from gitfourchette.benchmark import Benchmark
from gitfourchette.filewatcher import FileWatcher
from gitfourchette.hiddencommitsolver import HiddenCommitSolver
from gitfourchette.globalstatus import globalstatus
from gitfourchette.graph import Graph, GraphSplicer, KF_INTERVAL
from gitfourchette.qt import *
from gitfourchette.settings import BasePrefs
from typing import Iterable
import os
import pygit2


PROGRESS_INTERVAL = 5000


@dataclass
class BatchedOffset:
    batch: int
    offsetInBatch: int


def progressTick(progress, i, numCommitsBallpark=0):
    if i != 0 and i % PROGRESS_INTERVAL == 0:
        if numCommitsBallpark > 0 and i <= numCommitsBallpark:
            # Updating the text too often prevents progress bar from updating on macOS theme,
            # so don't use setLabelText if we're changing the progress value
            progress.setValue(i)
        else:
            progress.setLabelText(tr("{0} commits processed.").format(progress.locale().toString(i)))
        QCoreApplication.processEvents()
        if progress.wasCanceled():
            raise StopIteration()


class ForeignCommitSolver:
    def __init__(self, commitsToRefs):
        self._nextLocal = set()
        self.foreignCommits = set()
        for commitOid, refList in commitsToRefs.items():
            if any(name == 'HEAD' or name.startswith("refs/heads/") for name in refList):
                self._nextLocal.add(commitOid)

    def feed(self, commit: pygit2.Commit):
        if commit.oid in self._nextLocal:
            self._nextLocal.remove(commit.oid)
            for p in commit.parents:
                self._nextLocal.add(p.oid)
        else:
            self.foreignCommits.add(commit.oid)


@dataclass
class RepoPrefs(BasePrefs):
    filename = "prefs.json"
    _parentDir = ""

    draftCommitMessage: str = ""
    draftAmendMessage: str = ""
    hiddenBranches: list[str] = field(default_factory=list)

    def getParentDir(self):
        return self._parentDir


class RepoState:
    repo: pygit2.Repository

    # May be None; call initializeWalker before use.
    # Keep it around to speed up refreshing.
    walker: pygit2.Walker | None

    # ordered list of commits
    commitSequence: list[pygit2.Commit]
    # TODO PYGIT2 ^^^ do we want to store the actual commits? wouldn't the oids be enough? not for search though i guess...

    graph: Graph | None

    refCache: dict[str, pygit2.Oid]
    "Maps reference names to commit oids"

    reverseRefCache: dict[pygit2.Oid, list[str]]
    "Maps commit oids to reference names pointing to this commit"

    # path of superproject if this is a submodule
    superproject: str

    # oid of the active commit (to make it bold)
    activeCommitOid: pygit2.Oid | None

    # Everytime we refresh, new rows may be inserted at the top of the graph.
    # This may push existing rows down, away from the top of the graph.
    # To avoid recomputing offsetFromTop for every commit metadata,
    # we keep track of the general offset of every batch of rows created by every refresh.
    batchOffsets: list[int]

    commitPositions: dict[pygit2.Oid, BatchedOffset]

    currentBatchID: int

    mutex: QMutex

    foreignCommits: set[pygit2.Oid]

    hiddenCommits: set[pygit2.Oid]

    uiPrefs: RepoPrefs

    def __init__(self, repo: pygit2.Repository):
        self.repo = repo

        uiConfigPath = os.path.join(self.repo.path, settings.REPO_SETTINGS_DIR)
        self.uiPrefs = RepoPrefs()
        self.uiPrefs._parentDir = uiConfigPath

        # On Windows, core.autocrlf is usually set to true in the system config.
        # However, libgit2 cannot find the system config if git wasn't installed
        # with the official installer, e.g. via scoop. If a repo was cloned with
        # autocrlf=true, GF's staging area would be unusable on Windows without
        # setting autocrlf=true in the config.
        if WINDOWS and "core.autocrlf" not in self.repo.config:
            tempConfigPath = os.path.join(tempdir.getSessionTemporaryDirectory(), "gitconfig")
            log.info("RepoState", "Forcing core.autocrlf=true in: " + tempConfigPath)
            tempConfig = pygit2.Config(tempConfigPath)
            tempConfig["core.autocrlf"] = "true"
            self.repo.config.add_file(tempConfigPath, level=1)

        self.walker = None
        self.currentBatchID = 0

        self.commitSequence = []
        self.hiddenCommits = set()

        self.commitPositions = {}
        self.graph = None

        self.refCache = {}
        self.reverseRefCache = {}
        self.refreshRefCache()

        self.superproject = porcelain.getSuperproject(self.repo)

        self.activeCommitOid = None

        self.uiPrefs.load()

        self.resolveHiddenCommits()

        self.fileWatcher = FileWatcher(None, self.repo)

    @property
    def hiddenBranches(self):
        return self.uiPrefs.hiddenBranches

    @property
    def allocLanesInGaps(self):
        # Flattened graphs are easier to read when new lanes are always allocated to the right.
        # Non-flattened graphs look better if we try to fill up the gaps in the graph.
        return not settings.prefs.graph_flattenLanes

    def getDraftCommitMessage(self, forAmending = False) -> str:
        if forAmending:
            return self.uiPrefs.draftAmendMessage
        else:
            return self.uiPrefs.draftCommitMessage

    def setDraftCommitMessage(self, newMessage: str | None, forAmending: bool = False):
        if not newMessage:
            newMessage = ""
        if forAmending:
            self.uiPrefs.draftAmendMessage = newMessage
        else:
            self.uiPrefs.draftCommitMessage = newMessage
        self.uiPrefs.write()

    def refreshRefCache(self):
        self.refCache = porcelain.mapRefsToOids(self.repo)

        self.reverseRefCache = defaultdict(list)
        for k, v in self.refCache.items():
            self.reverseRefCache[v].append(k)

    @property
    def shortName(self) -> str:
        prefix = ""
        if self.superproject:
            superprojectNickname = settings.history.getRepoNickname(self.superproject)
            prefix = superprojectNickname + ": "

        return prefix + settings.history.getRepoNickname(self.repo.workdir)

    def getCommitSequentialIndex(self, oid: pygit2.Oid):
        position = self.commitPositions[oid]
        assert position.batch < len(self.batchOffsets)
        return self.batchOffsets[position.batch] + position.offsetInBatch

    def initializeWalker(self, tipOids: Iterable[pygit2.Oid]) -> pygit2.Walker:
        sorting = pygit2.GIT_SORT_TOPOLOGICAL

        if settings.prefs.graph_chronologicalOrder:
            # In strictly chronological ordering, a commit may appear before its
            # children if it was "created" later than its children. The graph
            # generator produces garbage in this case. So, for chronological
            # ordering, keep GIT_SORT_TOPOLOGICAL in addition to GIT_SORT_TIME.
            sorting |= pygit2.GIT_SORT_TIME

        if self.walker is None:
            self.walker = self.repo.walk(None, sorting)
        else:
            self.walker.sort(sorting)  # this resets the walker

        for tip in tipOids:
            self.walker.push(tip)

        return self.walker

    def updateActiveCommitOid(self):
        try:
            self.activeCommitOid = self.repo.head.target
        except pygit2.GitError:
            self.activeCommitOid = None

    def loadCommitSequence(self, progress: QProgressDialog):
        progress.setLabelText(tr("Processing commit log..."))
        QCoreApplication.processEvents()

        walker = self.initializeWalker(self.refCache.values())

        self.updateActiveCommitOid()

        bench = Benchmark("GRAND TOTAL"); bench.__enter__()

        commitSequence: list[pygit2.Commit] = []
        graph = Graph()

        # Retrieve the number of commits that we loaded last time we opened this repo
        # so we can estimate how long it'll take to load it again
        numCommitsBallpark = settings.history.getRepoNumCommits(self.repo.workdir)
        if numCommitsBallpark != 0:
            progress.setMinimum(0)
            progress.setMaximum(2 * numCommitsBallpark)  # reserve second half of progress bar for graph progress

        foreignCommitSolver = ForeignCommitSolver(self.reverseRefCache)
        hiddenCommitSolver = self.newHiddenCommitSolver()
        try:
            for offsetFromTop, commit in enumerate(walker):
                progressTick(progress, offsetFromTop, numCommitsBallpark)

                commitSequence.append(commit)
                self.commitPositions[commit.oid] = BatchedOffset(self.currentBatchID, offsetFromTop)

                foreignCommitSolver.feed(commit)
                hiddenCommitSolver.feed(commit)
        except StopIteration:
            pass

        log.info("loadCommitSequence", F"{self.shortName}: loaded {len(commitSequence):,} commits")
        progress.setLabelText(tr("Preparing graph..."))

        if numCommitsBallpark != 0:
            progress.setMinimum(-len(commitSequence))  # first half of progress bar was for commit log
        progress.setMaximum(len(commitSequence))

        graphGenerator = graph.startGenerator()
        for commit in commitSequence:
            graphGenerator.createArcsForNewCommit(commit.oid, commit.parent_ids, self.allocLanesInGaps)
            if graphGenerator.row % KF_INTERVAL == 0:
                progress.setValue(graphGenerator.row)
                QCoreApplication.processEvents()
                graph.saveKeyframe(graphGenerator)

        self.commitSequence = commitSequence
        self.foreignCommits = foreignCommitSolver.foreignCommits
        self.hiddenCommits = hiddenCommitSolver.hiddenCommits
        self.graph = graph
        self.batchOffsets = [0]
        self.currentBatchID = 0

        bench.__exit__(None, None, None)

        return commitSequence

    def loadTaintedCommitsOnly(self, oldRefCache: dict[str, pygit2.Oid]):
        self.currentBatchID += 1

        newCommitSequence = []

        oldHeads = oldRefCache.values()
        newHeads = self.refCache.values()

        with Benchmark("Init walker"):
            walker = self.initializeWalker(newHeads)

        graphSplicer = GraphSplicer(self.graph, oldHeads, newHeads)

        i = 0
        while graphSplicer.keepGoing:
            if i != 0 and i % PROGRESS_INTERVAL == 0:
                log.info("progress", "GraphSplicer commits processed:", i)
                QCoreApplication.processEvents()
            offsetFromTop = i
            i += 1

            try:
                commit: pygit2.Commit = next(walker)
            except StopIteration:
                break

            wasKnown = commit.oid in self.commitPositions
            self.commitPositions[commit.oid] = BatchedOffset(self.currentBatchID, offsetFromTop)

            newCommitSequence.append(commit)
            graphSplicer.spliceNewCommit(commit.oid, commit.parent_ids, wasKnown, self.allocLanesInGaps)

        graphSplicer.finish()

        if graphSplicer.foundEquilibrium:
            nRemoved = graphSplicer.equilibriumOldRow
            nAdded = graphSplicer.equilibriumNewRow
        else:
            nRemoved = -1  # We could use len(self.commitSequence), but -1 will force quickRefresh to replace the model wholesale
            nAdded = len(newCommitSequence)

        with Benchmark("Nuke unreachable commits from cache"):
            for trashedCommit in (graphSplicer.oldCommitsSeen - graphSplicer.newCommitsSeen):
                del self.commitPositions[trashedCommit]

        # Piece correct commit sequence back together
        with Benchmark("Reassemble commit sequence"):
            if not graphSplicer.foundEquilibrium:
                self.commitSequence = newCommitSequence
            elif nAdded == 0 and nRemoved == 0:
                pass
            elif nRemoved == 0:
                self.commitSequence = newCommitSequence[:nAdded] + self.commitSequence
            else:
                self.commitSequence = newCommitSequence[:nAdded] + self.commitSequence[nRemoved:]

        # Compute new batch offset
        assert self.currentBatchID == len(self.batchOffsets)
        self.batchOffsets = [previousOffset + graphSplicer.oldGraphRowOffset for previousOffset in self.batchOffsets]
        self.batchOffsets.append(0)

        # Resolve foreign commits
        # todo: this will do a pass on all commits. Can we look at fewer commits?
        with Benchmark("Resolve foreign/hidden commits"):
            foreignCommitSolver = ForeignCommitSolver(self.reverseRefCache)
            hiddenCommitSolver = self.newHiddenCommitSolver()
            for commit in self.commitSequence:
                foreignCommitSolver.feed(commit)
                hiddenCommitSolver.feed(commit)  # TODO: we can stop early by looking at hiddenCommitResolver.done; what about foreignCommitResolver?
            self.foreignCommits = foreignCommitSolver.foreignCommits
            self.hiddenCommits = hiddenCommitSolver.hiddenCommits

        self.updateActiveCommitOid()

        return nRemoved, nAdded

    def toggleHideBranch(self, branchName: str):
        if branchName not in self.hiddenBranches:
            self.hideBranch(branchName)
        else:
            self.unhideBranch(branchName)

    def hideBranch(self, branchName: str):
        if branchName in self.hiddenBranches:
            return
        self.uiPrefs.hiddenBranches.append(branchName)
        self.uiPrefs.write()
        self.resolveHiddenCommits()

    def unhideBranch(self, branchName: str):
        if branchName not in self.hiddenBranches:
            return
        self.uiPrefs.hiddenBranches.remove(branchName)
        self.uiPrefs.write()
        self.resolveHiddenCommits()

    def getHiddenBranchOids(self):
        seeds = set()

        def isSharedByVisibleBranch(oid):
            return any(
                refName for refName in self.reverseRefCache[oid]
                if refName not in self.hiddenBranches
                and not refName.startswith(porcelain.TAGS_PREFIX))

        hiddenBranches = self.hiddenBranches[:]
        for hiddenBranch in hiddenBranches:
            try:
                oid = self.refCache[hiddenBranch]
                if not isSharedByVisibleBranch(oid):
                    seeds.add(oid)
            except (KeyError, pygit2.InvalidSpecError):
                log.info("RepoState", "Skipping missing hidden branch: " + hiddenBranch)
                self.uiPrefs.hiddenBranches.remove(hiddenBranch)  # Remove it from prefs

        return seeds

    def newHiddenCommitSolver(self) -> HiddenCommitSolver:
        solver = HiddenCommitSolver()

        for hiddenBranchTip in self.getHiddenBranchOids():
            solver.hideCommit(hiddenBranchTip)

        if settings.prefs.debug_hideStashJunkParents:
            for stash in self.repo.listall_stashes():
                stashCommit: pygit2.Commit = self.repo[stash.commit_id].peel(pygit2.Commit)
                if len(stashCommit.parents) >= 2 and stashCommit.parents[1].raw_message.startswith(b"index on "):
                    solver.hideCommit(stashCommit.parents[1].id, force=True)
                if len(stashCommit.parents) >= 3 and stashCommit.parents[2].raw_message.startswith(b"untracked files on "):
                    solver.hideCommit(stashCommit.parents[2].id, force=True)

        return solver

    def resolveHiddenCommits(self):
        solver = self.newHiddenCommitSolver()
        for commit in self.commitSequence:
            solver.feed(commit)
            if solver.done:
                break
        self.hiddenCommits = solver.hiddenCommits
