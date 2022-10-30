from dataclasses import dataclass, field
from gitfourchette import log
from gitfourchette import porcelain, tempdir
from gitfourchette import settings
from gitfourchette.benchmark import Benchmark
from gitfourchette.filewatcher import FileWatcher
from gitfourchette.globalstatus import globalstatus
from gitfourchette.graph import Graph, GraphSplicer, KF_INTERVAL
from gitfourchette.qt import *
from gitfourchette.settings import BasePrefs
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
            progress.setLabelText(tr("{0:,} commits processed.").format(i))
        QCoreApplication.processEvents()
        if progress.wasCanceled():
            raise StopIteration()


class ForeignCommitSolver:
    def __init__(self, commitsToRefs):
        self._nextLocal = set()
        self.foreignCommits = set()
        for commitOid, refList in commitsToRefs.items():
            if any(name.startswith("refs/heads/") for name in refList):
                self._nextLocal.add(commitOid)

    def feed(self, commit: pygit2.Commit):
        if commit.oid in self._nextLocal:
            self._nextLocal.remove(commit.oid)
            for p in commit.parents:
                self._nextLocal.add(p.oid)
        else:
            self.foreignCommits.add(commit.oid)


class HiddenCommitSolver:
    def __init__(self, seeds):
        self._forceShow = set()
        self._nextHidden = set()
        self.hiddenCommits = set()
        for commitOid in seeds:
            self._nextHidden.add(commitOid)

    @property
    def done(self):
        return len(self._nextHidden) == 0

    def feed(self, commit: pygit2.Commit):
        if commit.oid in self._nextHidden:
            assert commit.oid not in self._forceShow
            self.hiddenCommits.add(commit.oid)
            self._nextHidden.remove(commit.oid)
            for p in commit.parents:
                if p.oid not in self._forceShow:
                    self._nextHidden.add(p.oid)
        else:
            try:
                self._forceShow.remove(commit.oid)
            except KeyError:
                pass

            for p in commit.parents:
                self._forceShow.add(p.oid)

                try:
                    self._nextHidden.remove(p.oid)
                except KeyError:
                    pass


@dataclass
class RepoPrefs(BasePrefs):
    filename = "prefs.json"
    _parentDir = ""

    draftMessage: str = ""
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

    commitPositions: dict[pygit2.Oid, BatchedOffset]

    graph: Graph | None

    # Set of head commits for every ref (required to refresh the commit graph)
    currentRefs: list[pygit2.Oid]

    # path of superproject if this is a submodule
    superproject: str | None

    # oid of the active commit (to make it bold)
    activeCommitOid: pygit2.Oid | None

    # Everytime we refresh, new rows may be inserted at the top of the graph.
    # This may push existing rows down, away from the top of the graph.
    # To avoid recomputing offsetFromTop for every commit metadata,
    # we keep track of the general offset of every batch of rows created by every refresh.
    batchOffsets: list[int]

    currentBatchID: int

    mutex: QMutex

    # commit oid --> list of reference names
    commitsToRefs: dict[pygit2.Oid, list[str]]

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
        if QSysInfo.productType() == "windows" and "core.autocrlf" not in self.repo.config:
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

        self.refreshRefsByCommitCache()

        self.superproject = porcelain.getSuperproject(self.repo)

        self.activeCommitOid = None

        self.currentRefs = []

        self.uiPrefs.load()

        self.resolveHiddenCommits()

        self.fileWatcher = FileWatcher(self.repo)

    @property
    def hiddenBranches(self):
        return self.uiPrefs.hiddenBranches

    def getDraftCommitMessage(self) -> str:
        return self.uiPrefs.draftMessage

    def setDraftCommitMessage(self, newMessage: str | None):
        if not newMessage:
            newMessage = ""
        self.uiPrefs.draftMessage = newMessage
        self.uiPrefs.write()

    def refreshRefsByCommitCache(self):
        self.commitsToRefs = porcelain.mapCommitsToReferences(self.repo)

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

    def initializeWalker(self, tipOids: list[pygit2.Oid]) -> pygit2.Walker:
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
        progress.setLabelText(tr("Gathering refs..."))
        QCoreApplication.processEvents()

        self.currentRefs = porcelain.getOidsForAllReferences(self.repo)

        walker = self.initializeWalker(self.currentRefs)

        self.updateActiveCommitOid()

        bench = Benchmark("GRAND TOTAL"); bench.__enter__()

        commitSequence: list[pygit2.Commit] = []
        graph = Graph()

        progress.setLabelText(tr("Processing commit log..."))

        # Retrieve the number of commits that we loaded last time we opened this repo
        # so we can estimate how long it'll take to load it again
        numCommitsBallpark = settings.history.getRepoNumCommits(self.repo.workdir)
        if numCommitsBallpark != 0:
            progress.setMinimum(0)
            progress.setMaximum(2 * numCommitsBallpark)  # reserve second half of progress bar for graph progress

        foreignCommitResolver = ForeignCommitSolver(self.commitsToRefs)
        hiddenCommitResolver = HiddenCommitSolver(self.getHiddenBranchOids())
        try:
            for offsetFromTop, commit in enumerate(walker):
                progressTick(progress, offsetFromTop, numCommitsBallpark)

                commitSequence.append(commit)
                self.commitPositions[commit.oid] = BatchedOffset(self.currentBatchID, offsetFromTop)

                foreignCommitResolver.feed(commit)
                hiddenCommitResolver.feed(commit)
        except StopIteration:
            pass

        log.info("loadCommitSequence", F"{self.shortName}: loaded {len(commitSequence):,} commits")
        progress.setLabelText(tr("Preparing graph..."))

        if numCommitsBallpark != 0:
            progress.setMinimum(-len(commitSequence))  # first half of progress bar was for commit log
        progress.setMaximum(len(commitSequence))

        graphGenerator = graph.startGenerator()
        for commit in commitSequence:
            graphGenerator.createArcsForNewCommit(commit.oid, commit.parent_ids)
            if graphGenerator.row % KF_INTERVAL == 0:
                progress.setValue(graphGenerator.row)
                QCoreApplication.processEvents()
                graph.saveKeyframe(graphGenerator)

        self.commitSequence = commitSequence
        self.foreignCommits = foreignCommitResolver.foreignCommits
        self.hiddenCommits = hiddenCommitResolver.hiddenCommits
        self.graph = graph
        self.batchOffsets = [0]
        self.currentBatchID = 0

        bench.__exit__(None, None, None)

        return commitSequence

    def loadTaintedCommitsOnly(self):
        globalstatus.setText(tr("{0}: Checking for new commits...").format(self.shortName))

        self.currentBatchID += 1

        globalstatus.setProgressMaximum(5)
        globalstatus.setProgressValue(1)

        newCommitSequence = []

        oldHeads = self.currentRefs
        with Benchmark("Get new heads"):
            newHeads = porcelain.getOidsForAllReferences(self.repo)

        with Benchmark("Init walker"):
            walker = self.initializeWalker(newHeads)

        graphSplicer = GraphSplicer(self.graph, oldHeads, newHeads)

        globalstatus.setProgressValue(2)

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
            graphSplicer.spliceNewCommit(commit.oid, commit.parent_ids, wasKnown)

        graphSplicer.finish()

        if graphSplicer.foundEquilibrium:
            nRemoved = graphSplicer.equilibriumOldRow
            nAdded = graphSplicer.equilibriumNewRow
        else:
            nRemoved = -1  # We could use len(self.commitSequence), but -1 will force quickRefresh to replace the model wholesale
            nAdded = len(newCommitSequence)

        globalstatus.setProgressValue(3)

        with Benchmark("Nuke unreachable commits from cache"):
            for trashedCommit in (graphSplicer.oldCommitsSeen - graphSplicer.newCommitsSeen):
                del self.commitPositions[trashedCommit]

        # Piece correct commit sequence back together
        if graphSplicer.foundEquilibrium:
            self.commitSequence = newCommitSequence[:nAdded] + self.commitSequence[nRemoved:]
        else:
            self.commitSequence = newCommitSequence
        self.currentRefs = newHeads

        # Compute new batch offset
        assert self.currentBatchID == len(self.batchOffsets)
        self.batchOffsets = [previousOffset + graphSplicer.oldGraphRowOffset for previousOffset in self.batchOffsets]
        self.batchOffsets.append(0)

        # Resolve foreign commits
        # todo: this will do a pass on all commits. Can we look at fewer commits?
        foreignCommitResolver = ForeignCommitSolver(self.commitsToRefs)
        hiddenCommitResolver = HiddenCommitSolver(self.getHiddenBranchOids())
        for commit in self.commitSequence:
            foreignCommitResolver.feed(commit)
            hiddenCommitResolver.feed(commit)  # TODO: we can stop early by looking at hiddenCommitResolver.done; what about foreignCommitResolver?
        self.foreignCommits = foreignCommitResolver.foreignCommits
        self.hiddenCommits = hiddenCommitResolver.hiddenCommits

        globalstatus.setProgressValue(4)

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
                refName for refName in self.commitsToRefs[oid]
                if refName not in self.hiddenBranches
                and not refName.startswith('refs/tags/'))

        for hiddenBranch in self.hiddenBranches:
            try:
                commit: pygit2.Commit = self.repo.lookup_reference(hiddenBranch).peel(pygit2.Commit)
                if not isSharedByVisibleBranch(commit.oid):
                    seeds.add(commit.oid)
            except pygit2.InvalidSpecError:
                log.info("RepoState", "Skipping invalid spec for hidden branch: " + hiddenBranch)
                pass

        return seeds

    def resolveHiddenCommits(self):
        hiddenCommitResolver = HiddenCommitSolver(self.getHiddenBranchOids())
        for commit in self.commitSequence:
            hiddenCommitResolver.feed(commit)
            if hiddenCommitResolver.done:
                break
        self.hiddenCommits = hiddenCommitResolver.hiddenCommits
