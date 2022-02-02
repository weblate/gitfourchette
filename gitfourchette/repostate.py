from actionflows import ActionFlows
from allgit import *
from allqt import *
from benchmark import Benchmark
from collections import defaultdict
from dataclasses import dataclass
from globalstatus import globalstatus
from graph import Graph, GraphSplicer, KF_INTERVAL
import os
import porcelain
import settings


PROGRESS_INTERVAL = 5000
SETTING_KEY_DRAFT_MESSAGE = "DraftMessage"


@dataclass
class BatchedOffset:
    batch: int
    offsetInBatch: int


class RepoState:
    repo: Repository
    settings: QSettings

    # May be None; call initializeWalker before use.
    # Keep it around to speed up refreshing.
    walker: Walker | None

    # ordered list of commits
    commitSequence: list[Commit]
    # TODO PYGIT2 ^^^ do we want to store the actual commits? wouldn't the oids be enough? not for search though i guess...

    commitPositions: dict[Oid, BatchedOffset]

    graph: Graph | None

    # Set of head commits for every ref (required to refresh the commit graph)
    currentRefs: list[Oid]

    # path of superproject if this is a submodule
    superproject: str | None

    # oid of the active commit (to make it bold)
    activeCommitOid: Oid | None

    # Everytime we refresh, new rows may be inserted at the top of the graph.
    # This may push existing rows down, away from the top of the graph.
    # To avoid recomputing offsetFromTop for every commit metadata,
    # we keep track of the general offset of every batch of rows created by every refresh.
    batchOffsets: list[int]

    currentBatchID: int

    mutex: QMutex

    # commit oid --> list of reference names
    refsByCommit: defaultdict[Oid, list[str]]

    def __init__(self, dir):
        self.repo = Repository(dir)
        self.walker = None
        self.currentBatchID = 0

        self.commitSequence = []
        self.commitPositions = {}
        self.graph = None

        self.refsByCommit = defaultdict(list)
        self.refreshRefsByCommitCache()

        print("TODO: parse superproject")
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
        self.refsByCommit.clear()
        refKey: str
        for refKey in self.repo.references:
            ref: Reference = self.repo.references[refKey]
            if type(ref.target) != Oid:
                print(F"Skipping symbolic reference {refKey} --> {ref.target}")
                continue
            assert refKey.startswith('refs/')
            if refKey == "refs/stash":
                continue
            self.refsByCommit[ref.target].append(refKey)

        for stashIndex, stash in enumerate(self.repo.listall_stashes()):
            self.refsByCommit[stash.commit_id].append(F"stash@{{{stashIndex}}}")

    @property
    def shortName(self) -> str:
        prefix = ""
        if self.superproject:
            superprojectNickname = settings.history.getRepoNickname(self.superproject)
            prefix = superprojectNickname + ": "

        return prefix + settings.history.getRepoNickname(self.repo.workdir)

    def getCommitSequentialIndex(self, oid: Oid):
        position = self.commitPositions[oid]
        assert position.batch < len(self.batchOffsets)
        return self.batchOffsets[position.batch] + position.offsetInBatch

    def initializeWalker(self, tipOids: list[Oid]) -> Walker:
        if settings.prefs.graph_topoOrder:
            sorting = GIT_SORT_TOPOLOGICAL
        else:
            sorting = GIT_SORT_TIME

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

        commitSequence: list[Commit] = []
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
    def traceOneCommitAvailability(nextLocal: set, meta: Commit):
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
            if i % PROGRESS_INTERVAL == 0:
                print("Commits processed:", i)
                QCoreApplication.processEvents()
            offsetFromTop = i
            i += 1

            try:
                commit: Commit = next(walker)
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

