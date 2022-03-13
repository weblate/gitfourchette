from collections import defaultdict
from dataclasses import dataclass
from gitfourchette import log
from gitfourchette import porcelain, tempdir
from gitfourchette import settings
from gitfourchette.benchmark import Benchmark
from gitfourchette.globalstatus import globalstatus
from gitfourchette.graph import Graph, GraphSplicer, KF_INTERVAL
from gitfourchette.qt import *
import os
import pygit2


PROGRESS_INTERVAL = 5000
SETTING_KEY_DRAFT_MESSAGE = "DraftMessage"


@dataclass
class BatchedOffset:
    batch: int
    offsetInBatch: int


class ShallowRepoNotSupportedError(BaseException):
    pass


class RepoState:
    repo: pygit2.Repository
    settings: QSettings

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
    refsByCommit: dict[pygit2.Oid, list[str]]

    def __init__(self, dir):
        self.repo = pygit2.Repository(dir)

        if self.repo.is_shallow:
            raise ShallowRepoNotSupportedError()

        # On Windows, core.autocrlf is usually set to true in the system config.
        # However, libgit2 cannot find the system config if git wasn't installed
        # with the official installer, e.g. via scoop. If a repo was cloned with
        # autocrlf=true, GF's staging area would be unusable on Windows without
        # setting autocrlf=true in the config.
        if QSysInfo.productType() == "windows" and "core.autocrlf" not in self.repo.config:
            tempConfigPath = os.path.join(tempdir.getSessionTemporaryDirectory(), "gitconfig")
            print("Forcing core.autocrlf=true in:", tempConfigPath)
            tempConfig = pygit2.Config(tempConfigPath)
            tempConfig["core.autocrlf"] = "true"
            self.repo.config.add_file(tempConfigPath, level=1)

        self.walker = None
        self.currentBatchID = 0

        self.commitSequence = []
        self.commitPositions = {}
        self.graph = None

        self.refsByCommit = defaultdict(list)
        self.refreshRefsByCommitCache()

        log.info("TODO", "parse superproject")
        self.superproject = None
        #self.superproject = self.repo.git.rev_parse("--show-superproject-working-tree")

        self.activeCommitOid = None

        self.currentRefs = []

        repoConfigPath = os.path.join(self.repo.path, settings.REPO_SETTINGS_DIR, "config.ini")
        self.settings = QSettings(repoConfigPath, QSettings.IniFormat)

    def getDraftCommitMessage(self) -> str:
        return self.settings.value(SETTING_KEY_DRAFT_MESSAGE, "")

    def setDraftCommitMessage(self, newMessage: str | None):
        if not newMessage:
            self.settings.remove(SETTING_KEY_DRAFT_MESSAGE)
        else:
            self.settings.setValue(SETTING_KEY_DRAFT_MESSAGE, newMessage)

    def refreshRefsByCommitCache(self):
        self.refsByCommit = porcelain.mapCommitsToReferences(self.repo)

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
        if settings.prefs.graph_topoOrder:
            sorting = pygit2.GIT_SORT_TOPOLOGICAL
        else:
            sorting = pygit2.GIT_SORT_TIME

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

    def loadCommitList(self, progress: QProgressDialog):
        progress.setLabelText(F"Preparing refs...")
        QCoreApplication.processEvents()

        self.currentRefs = porcelain.getOidsForAllReferences(self.repo)

        walker = self.initializeWalker(self.currentRefs)

        self.updateActiveCommitOid()

        bench = Benchmark("GRAND TOTAL"); bench.__enter__()

        commitSequence: list[pygit2.Commit] = []
        #commit
        # refs = {}
        graph = Graph()
        nextLocal = set()

        progress.setLabelText(F"Preparing walk...")
        QCoreApplication.processEvents()

        i = 0
        for commit in walker:
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

            commitSequence.append(commit)
            self.commitPositions[commit.oid] = BatchedOffset(self.currentBatchID, offsetFromTop)

            #TODO self.traceOneCommitAvailability(nextLocal, meta)

        globalstatus.setText(F"{self.shortName}: loaded {len(commitSequence):,} commits")

        progress.setLabelText("Preparing graph...")
        progress.setMaximum(len(commitSequence))
        graphGenerator = graph.startGenerator()
        for commit in commitSequence:
            graphGenerator.createArcsForNewCommit(commit.oid, commit.parent_ids)
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
    def traceOneCommitAvailability(nextLocal: set, meta: pygit2.Commit):
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

        # todo: this will do a pass on all commits. Can we look at fewer commits?
        self.traceCommitAvailability(self.commitSequence)

        globalstatus.setProgressValue(4)

        self.updateActiveCommitOid()

        return nRemoved, nAdded

    @staticmethod
    def traceCommitAvailability(metas, progressTick=None):
        """ TODO
        nextLocal = set()
        for i, meta in enumerate(metas):
            if progressTick is not None and 0 == i % PROGRESS_INTERVAL:
                progressTick(i)
            RepoState.traceOneCommitAvailability(nextLocal, meta)
        assert len(nextLocal) == 0, "there are unreachable commits at the bottom of the graph"
        """
        pass

