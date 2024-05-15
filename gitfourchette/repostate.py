import logging
import os
from collections import defaultdict
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Iterable

from gitfourchette import settings
from gitfourchette.graph import Graph, GraphSplicer
from gitfourchette.graphtrickle import GraphTrickle
from gitfourchette.porcelain import *
from gitfourchette.prefsfile import PrefsFile
from gitfourchette.qt import *
from gitfourchette.toolbox import *

logger = logging.getLogger(__name__)

UC_FAKEID = "UC_FAKEID"


def toggleListElement(l: list, e):
    assert isinstance(l, list)
    try:
        l.remove(e)
        return False
    except ValueError:
        l.append(e)
        return True


def toggleSetElement(l: set, e):
    assert isinstance(l, set)
    try:
        l.remove(e)
        return False
    except KeyError:
        l.add(e)
        return True


@dataclass
class RepoPrefs(PrefsFile):
    _filename = f"{APP_SYSTEM_NAME}.json"
    _allowMakeDirs = False
    _parentDir = ""

    draftCommitMessage: str = ""
    draftCommitSignature: Signature = None
    draftAmendMessage: str = ""
    hiddenRefPatterns: set = field(default_factory=set)
    hiddenStashCommits: list = field(default_factory=list)
    collapseCache: list = field(default_factory=list)
    hideAllStashes: bool = False

    def getParentDir(self):
        return self._parentDir


class RepoState(QObject):
    loadingProgress: Signal()

    repo: Repo

    # May be None; call initializeWalker before use.
    # Keep it around to speed up refreshing.
    walker: Walker | None

    # ordered list of commits
    commitSequence: list[Commit]
    # TODO PYGIT2 ^^^ do we want to store the actual commits? wouldn't the oids be enough? not for search though i guess...

    truncatedHistory: bool

    graph: Graph | None

    refCache: dict[str, Oid]
    "Maps reference names to commit oids"

    reverseRefCache: dict[Oid, list[str]]
    "Maps commit oids to reference names pointing to this commit"

    mergeheadsCache: list[Oid]

    # path of superproject if this is a submodule
    superproject: str

    # oid of the active commit (to make it bold)
    activeCommitOid: Oid | None

    foreignCommits: set[Oid]
    """Use this to look up which commits are part of local branches,
    and which commits are 'foreign'."""

    hiddenRefs: set[str]
    hiddenCommits: set[Oid]

    workdirStale: bool
    numUncommittedChanges: int

    headIsDetached: bool
    homeBranch: str

    uiPrefs: RepoPrefs

    def __init__(self, parent: QObject, repo: Repo):
        super().__init__(parent)

        assert isinstance(repo, Repo)
        self.repo = repo

        self.uiPrefs = RepoPrefs()
        self.uiPrefs._parentDir = self.repo.path

        self.walker = None

        self.commitSequence = []
        self.truncatedHistory = True

        self.graph = None
        self.localCommits = None

        self.headIsDetached = False
        self.homeBranch = ""
        self.refCache = {}
        self.reverseRefCache = {}
        self.mergeheadsCache = []
        self.hiddenRefs = set()
        self.hiddenCommits = set()

        self.uiPrefs.load()

        # Refresh ref cache after loading prefs (prefs contain hidden ref patterns)
        self.refreshRefCache()
        self.refreshMergeheadsCache()

        self.superproject = repo.get_superproject()

        self.activeCommitOid = None

        self.workdirStale = True
        self.numUncommittedChanges = 0

        self.resolveHiddenCommits()

    @property
    def numRealCommits(self):
        # The first item in the commit sequence is the "fake commit" for Uncommitted Changes.
        return max(0, len(self.commitSequence) - 1)

    def getDraftCommitMessage(self, forAmending = False) -> str:
        if forAmending:
            return self.uiPrefs.draftAmendMessage
        else:
            return self.uiPrefs.draftCommitMessage

    def getDraftCommitAuthor(self) -> Signature:
        return self.uiPrefs.draftCommitSignature

    def setDraftCommitMessage(
            self,
            message: str | None,
            author: Signature | None = None,
            forAmending: bool = False):
        if not message:
            message = ""
        if forAmending:
            self.uiPrefs.draftAmendMessage = message
        else:
            self.uiPrefs.draftCommitMessage = message
            self.uiPrefs.draftCommitSignature = author
        self.uiPrefs.write()

    @benchmark
    def refreshRefCache(self):
        """ Refresh refCache and reverseRefCache.

        Return True if there were any changes in the refs since the last
        refresh, or False if nothing changed.
        """

        self.headIsDetached = self.repo.head_is_detached

        if self.headIsDetached or self.repo.head_is_unborn:
            self.homeBranch = ""
        else:
            self.homeBranch = self.repo.head_branch_shorthand

        refCache = self.repo.map_refs_to_oids()

        if refCache == self.refCache:
            # Make sure it's sorted in the exact same order...
            if settings.DEVDEBUG:
                assert list(refCache.keys()) == list(self.refCache.keys()), "refCache key order changed! how did that happen?"

            # Nothing to do!
            return False

        reverseRefCache = defaultdict(list)
        for k, v in refCache.items():
            reverseRefCache[v].append(k)

        self.refCache = refCache
        self.reverseRefCache = reverseRefCache

        # Since the refs have changed, we need to refresh hidden refs
        self.refreshHiddenRefCache()

        return True

    @benchmark
    def refreshMergeheadsCache(self):
        mh = self.repo.listall_mergeheads()
        if mh != self.mergeheadsCache:
            self.mergeheadsCache = mh
            return True
        return False

    @property
    def shortName(self) -> str:
        prefix = ""
        if self.superproject:
            superprojectNickname = settings.history.getRepoNickname(self.superproject)
            prefix = superprojectNickname + ": "

        return prefix + settings.history.getRepoNickname(self.repo.workdir)

    @benchmark
    def initializeWalker(self, tipOids: Iterable[Oid]) -> Walker:
        sorting = SortMode.TOPOLOGICAL

        if settings.prefs.chronologicalOrder:
            # In strictly chronological ordering, a commit may appear before its
            # children if it was "created" later than its children. The graph
            # generator produces garbage in this case. So, for chronological
            # ordering, keep TOPOLOGICAL in addition to TIME.
            sorting |= SortMode.TIME

        if self.walker is None:
            self.walker = self.repo.walk(None, sorting)
        else:
            self.walker.reset()
            self.walker.sort(sorting)  # this resets the walker IF ALREADY WALKING (i.e. next was called once)

        # In topological mode, the order in which the tips are pushed is
        # significant (last in, first out). The tips should be pre-sorted in
        # ASCENDING chronological order so that the latest modified branches
        # come out at the top of the graph in topological mode.
        for tip in tipOids:
            self.walker.push(tip)

        return self.walker

    def updateActiveCommitOid(self):
        try:
            self.activeCommitOid = self.repo.head.target
        except GitError:
            self.activeCommitOid = None

    def _uncommittedChangesFakeCommitParents(self):
        try:
            head = self.refCache["HEAD"]
            return [head] + self.mergeheadsCache
        except KeyError:  # Unborn HEAD
            return []

    @property
    def nextTruncationThreshold(self) -> int:
        n = self.numRealCommits * 2
        n -= n % -1000  # round up to next thousand
        return max(n, settings.prefs.maxCommits)

    @benchmark
    def loadChangedRefs(self, oldRefCache: dict[str, Oid]):
        # DO NOT call processEvents() here. While splicing a large amount of
        # commits, GraphView may try to repaint an incomplete graph.
        # GraphView somehow ignores setUpdatesEnabled(False) here!

        newCommitSequence = []

        oldHeads = oldRefCache.values()
        newHeads = self.refCache.values()

        graphSplicer = GraphSplicer(self.graph, oldHeads, newHeads)
        newHiddenCommitSolver = self.newHiddenCommitSolver()
        newForeignCommitSolver = self.newForeignCommitSolver()

        # Generate fake "Uncommitted Changes" with HEAD as parent
        newCommitSequence.insert(0, None)
        graphSplicer.spliceNewCommit(UC_FAKEID, self._uncommittedChangesFakeCommitParents())

        if graphSplicer.keepGoing:
            with Benchmark("Walk graph until equilibrium"):
                walker = self.initializeWalker(newHeads)
                for commit in walker:
                    oid = commit.oid
                    parents = commit.parent_ids

                    newCommitSequence.append(commit)
                    graphSplicer.spliceNewCommit(oid, parents)

                    newHiddenCommitSolver.newCommit(oid, parents, self.hiddenCommits, discard=True)
                    newForeignCommitSolver.newCommit(oid, parents, self.foreignCommits, discard=True)

                    if not graphSplicer.keepGoing:
                        break

        graphSplicer.finish()

        if graphSplicer.foundEquilibrium:
            nRemoved = graphSplicer.equilibriumOldRow
            nAdded = graphSplicer.equilibriumNewRow
        else:
            nRemoved = -1  # We could use len(self.commitSequence), but -1 will force refreshRepo to replace the model wholesale
            nAdded = len(newCommitSequence)

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

        self.updateActiveCommitOid()

        return nRemoved, nAdded

    @benchmark
    def toggleHideRefPattern(self, refPattern: str):
        toggleSetElement(self.uiPrefs.hiddenRefPatterns, refPattern)
        self.uiPrefs.setDirty()
        self.refreshHiddenRefCache()
        self.resolveHiddenCommits()

    @benchmark
    def toggleHideStash(self, stashOid: Oid):
        toggleListElement(self.uiPrefs.hiddenStashCommits, stashOid.hex)
        self.uiPrefs.setDirty()
        self.resolveHiddenCommits()

    @benchmark
    def toggleHideAllStashes(self):
        self.uiPrefs.hideAllStashes = not self.uiPrefs.hideAllStashes
        self.uiPrefs.setDirty()
        self.resolveHiddenCommits()

    @benchmark
    def refreshHiddenRefCache(self):
        assert type(self.hiddenRefs) is set
        hiddenRefs = self.hiddenRefs
        hiddenRefs.clear()

        patterns = self.uiPrefs.hiddenRefPatterns
        if not patterns:
            return

        assert type(patterns) is set
        patternsSeen = set()

        for ref in self.refCache:
            if ref in patterns:
                hiddenRefs.add(ref)
                patternsSeen.add(ref)
            else:
                i = len(ref)
                while i >= 0:
                    i = ref.rfind('/', 0, i)
                    if i < 0:
                        break
                    prefix = ref[:i+1]
                    if prefix in patterns:
                        hiddenRefs.add(ref)
                        patternsSeen.add(prefix)
                        break

        if len(patternsSeen) != len(patterns):
            logger.debug(f"Culling stale hidden ref patterns {patterns - patternsSeen}")
            self.uiPrefs.hiddenRefPatterns = patternsSeen
            self.uiPrefs.setDirty()

    def getHiddenTips(self) -> set[Oid]:
        seeds = set()
        hiddenRefs = self.hiddenRefs

        def isSharedByVisibleBranch(oid: Oid):
            return any(
                ref for ref in self.reverseRefCache[oid]
                if ref not in hiddenRefs and not ref.startswith(RefPrefix.TAGS))

        for ref in hiddenRefs:
            oid = self.refCache[ref]
            if not isSharedByVisibleBranch(oid):
                seeds.add(oid)

        if self.uiPrefs.hideAllStashes:
            for refName, oid in self.refCache.items():
                if refName.startswith("stash@{"):
                    seeds.add(oid)
        else:
            hiddenStashCommits = self.uiPrefs.hiddenStashCommits[:]
            for hiddenStash in hiddenStashCommits:
                oid = Oid(hex=hiddenStash)
                if oid in self.reverseRefCache:
                    seeds.add(oid)
                else:
                    # Remove it from prefs
                    logger.info(f"Skipping missing hidden stash: {hiddenStash}")
                    self.uiPrefs.hiddenStashCommits.remove(hiddenStash)

        return seeds

    def newHiddenCommitSolver(self) -> GraphTrickle:
        trickle = GraphTrickle()

        # Explicitly show all refs by default
        for head in self.refCache.values():
            trickle.setEnd(head)

        # Explicitly hide tips
        for hiddenBranchTip in self.getHiddenTips():
            trickle.setPipe(hiddenBranchTip)

        # Explicitly hide stash junk parents
        if settings.prefs.hideStashJunkParents:
            for stash in self.repo.listall_stashes():
                stashCommit = self.repo.peel_commit(stash.commit_id)
                for i, parent in enumerate(stashCommit.parent_ids):
                    if i > 0:
                        trickle.setTap(parent)

        return trickle

    @benchmark
    def resolveHiddenCommits(self):
        self.hiddenCommits = set()
        solver = self.newHiddenCommitSolver()
        for i, commit in enumerate(self.commitSequence):
            if not commit:  # May be a fake commit such as Uncommitted Changes
                continue
            solver.newCommit(commit.oid, commit.parent_ids, self.hiddenCommits)
            # Don't check if trickle is complete too often (expensive)
            if (i % 250 == 0) and solver.done:
                logger.debug(f"resolveHiddenCommits complete in {i} iterations")
                break

    def newForeignCommitSolver(self) -> GraphTrickle:
        trickle = GraphTrickle()

        for oid, refList in self.reverseRefCache.items():
            assert oid not in trickle.frontier
            isLocal = any(name == 'HEAD' or name.startswith("refs/heads/") for name in refList)
            if isLocal:
                trickle.setEnd(oid)
            else:
                trickle.setPipe(oid)

        return trickle
