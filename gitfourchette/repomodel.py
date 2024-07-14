import logging
from collections import defaultdict
from typing import Generator

from gitfourchette import settings
from gitfourchette.graph import Graph, GraphSplicer
from gitfourchette.graphtrickle import GraphTrickle
from gitfourchette.porcelain import *
from gitfourchette.repoprefs import RepoPrefs
from gitfourchette.toolbox import *

logger = logging.getLogger(__name__)

UC_FAKEID = "UC_FAKEID"


def toggleSetElement(s: set, element):
    assert isinstance(s, set)
    try:
        s.remove(element)
        return False
    except KeyError:
        s.add(element)
        return True


class RepoModel:
    repo: Repo

    walker: Walker | None
    """Walker used to generate the graph. Call initializeWalker before use.
    Keep it around to speed up ulterior refreshes."""

    commitSequence: list[Commit]
    "Ordered list of commits."
    # TODO PYGIT2 ^^^ do we want to store the actual commits? wouldn't the oids be enough? not for search though i guess...

    truncatedHistory: bool

    graph: Graph | None

    refs: dict[str, Oid]
    "Maps reference names to commit oids"

    refsByOid: dict[Oid, list[str]]
    "Maps commit oids to reference names pointing to this commit"

    mergeheads: list[Oid]

    stashes: list[Oid]

    submodules: dict[str, str]

    superproject: str
    "Path of the superproject. Empty string if this isn't a submodule."

    headCommitId: Oid
    "Oid of the currently checked-out commit."

    foreignCommits: set[Oid]
    """Use this to look up which commits are part of local branches,
    and which commits are 'foreign'."""

    hiddenRefs: set[str]
    "All cached refs that are hidden, either explicitly or via ref patterns."

    hiddenCommits: set[Oid]
    "All cached commit oids that are hidden."

    workdirStale: bool
    "Flag indicating that the workdir should be refreshed before use."

    numUncommittedChanges: int
    "Number of unstaged+staged files. Zero means unknown count, not zero files."

    headIsDetached: bool
    homeBranch: str

    prefs: RepoPrefs

    def __init__(self, repo: Repo):
        assert isinstance(repo, Repo)

        self.commitSequence = []
        self.truncatedHistory = True

        self.walker = None
        self.graph = None

        self.headIsDetached = False
        self.headCommitId = NULL_OID
        self.homeBranch = ""

        self.superproject = ""
        self.workdirStale = True
        self.numUncommittedChanges = 0

        self.refs = {}
        self.refsByOid = {}
        self.mergeheads = []
        self.stashes = []
        self.submodules = {}
        self.remotes = []

        self.hiddenRefs = set()
        self.hiddenCommits = set()

        self.repo = repo

        self.prefs = RepoPrefs(repo)
        self.prefs._parentDir = repo.path
        self.prefs.load()

        # Prime ref cache after loading prefs (prefs contain hidden ref patterns)
        self.syncRefs()
        self.syncMergeheads()
        self.syncStashes()
        self.syncSubmodules()
        self.syncRemotes()
        self.superproject = repo.get_superproject()
        self.resolveHiddenCommits()

    @property
    def numRealCommits(self):
        # The first item in the commit sequence is the "fake commit" for Uncommitted Changes.
        return max(0, len(self.commitSequence) - 1)

    @benchmark
    def syncRefs(self):
        """ Refresh refCache and reverseRefCache.

        Return True if there were any changes in the refs since the last
        refresh, or False if nothing changed.
        """

        self.headIsDetached = self.repo.head_is_detached

        if self.headIsDetached or self.repo.head_is_unborn:
            self.homeBranch = ""
        else:
            self.homeBranch = self.repo.head_branch_shorthand

        refCache = self.repo.map_refs_to_ids(include_stashes=False)

        if refCache == self.refs:
            # Make sure it's sorted in the exact same order...
            if settings.DEVDEBUG:
                assert list(refCache.keys()) == list(self.refs.keys()), "refCache key order changed! how did that happen?"

            # Nothing to do!
            return False

        reverseRefCache = defaultdict(list)
        for k, v in refCache.items():
            reverseRefCache[v].append(k)

        self.refs = refCache
        self.refsByOid = reverseRefCache

        # Since the refs have changed, we need to refresh hidden refs
        self.refreshHiddenRefCache()

        return True

    @benchmark
    def syncMergeheads(self):
        mh = self.repo.listall_mergeheads()
        if mh != self.mergeheads:
            self.mergeheads = mh
            return True
        return False

    @benchmark
    def syncStashes(self):
        stashes = []
        for stash in self.repo.listall_stashes():
            stashes.append(stash.commit_id)
        if stashes != self.stashes:
            self.stashes = stashes
            return True
        return False

    @benchmark
    def syncSubmodules(self):
        submodules = self.repo.listall_submodules_dict()
        if submodules != self.submodules:
            self.submodules = submodules
            return True
        return False

    @benchmark
    def syncRemotes(self):
        # We could infer remote names from refCache, but we don't want
        # to miss any "blank" remotes that don't have any branches yet.
        # RemoteCollection.names() is much faster than iterating on RemoteCollection itself
        remotes = list(self.repo.remotes.names())
        if remotes != self.remotes:
            self.remotes = remotes
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
    def primeWalker(self) -> Walker:
        tipIds = self.refs.values()
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
        for tip in tipIds:
            self.walker.push(tip)

        return self.walker

    def syncHeadCommitId(self):
        oldHead = self.headCommitId
        try:
            self.headCommitId = self.repo.head.target
        except GitError:
            self.headCommitId = NULL_OID
        return oldHead != self.headCommitId

    def _uncommittedChangesFakeCommitParents(self):
        try:
            head = self.refs["HEAD"]
            return [head] + self.mergeheads
        except KeyError:  # Unborn HEAD
            return []

    @property
    def nextTruncationThreshold(self) -> int:
        n = self.numRealCommits * 2
        n -= n % -1000  # round up to next thousand
        return max(n, settings.prefs.maxCommits)

    def dangerouslyDetachedHead(self):
        if not self.headIsDetached:
            return False

        try:
            headTips = self.refsByOid[self.headCommitId]
        except KeyError:
            return False

        if headTips != ["HEAD"]:
            return False

        try:
            frame = self.graph.getCommitFrame(self.headCommitId)
        except KeyError:
            # Head commit not in graph, cannot determine if dangerous, err on side of caution
            return True

        arcs = list(frame.getArcsClosedByCommit())

        if len(arcs) == 0:
            return True

        if len(arcs) != 1:
            return False

        return arcs[0].openedBy == UC_FAKEID

    @benchmark
    def syncTopOfGraph(self, oldRefs: dict[str, Oid]):
        # DO NOT call processEvents() here. While splicing a large amount of
        # commits, GraphView may try to repaint an incomplete graph.
        # GraphView somehow ignores setUpdatesEnabled(False) here!

        newCommitSequence = []

        oldHeads = oldRefs.values()
        newHeads = self.refs.values()

        graphSplicer = GraphSplicer(self.graph, oldHeads, newHeads)
        newHiddenCommitSolver = self.newHiddenCommitSolver()
        newForeignCommitSolver = self.newForeignCommitSolver()

        # Generate fake "Uncommitted Changes" with HEAD as parent
        newCommitSequence.insert(0, None)
        graphSplicer.spliceNewCommit(UC_FAKEID, self._uncommittedChangesFakeCommitParents())

        if graphSplicer.keepGoing:
            with Benchmark("Walk graph until equilibrium"):
                walker = self.primeWalker()
                for commit in walker:
                    oid = commit.id
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

        return nRemoved, nAdded

    @benchmark
    def toggleHideRefPattern(self, refPattern: str):
        toggleSetElement(self.prefs.hiddenRefPatterns, refPattern)
        self.prefs.setDirty()
        self.refreshHiddenRefCache()
        self.resolveHiddenCommits()

    @benchmark
    def refreshHiddenRefCache(self):
        assert type(self.hiddenRefs) is set
        hiddenRefs = self.hiddenRefs
        hiddenRefs.clear()

        patterns = self.prefs.hiddenRefPatterns
        if not patterns:
            return

        assert type(patterns) is set
        patternsSeen = set()

        for ref in self.refs:
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
            self.prefs.hiddenRefPatterns = patternsSeen
            self.prefs.setDirty()

    def getHiddenTips(self) -> set[Oid]:
        seeds = set()
        hiddenRefs = self.hiddenRefs

        def isSharedByVisibleBranch(oid: Oid):
            return any(
                ref for ref in self.refsByOid[oid]
                if ref not in hiddenRefs and not ref.startswith(RefPrefix.TAGS))

        for ref in hiddenRefs:
            oid = self.refs[ref]
            if not isSharedByVisibleBranch(oid):
                seeds.add(oid)

        return seeds

    def commitsMatchingRefPattern(self, refPattern: str) -> Generator[Oid, None, None]:
        if not refPattern.endswith("/"):
            # Explicit ref
            try:
                yield self.refs[refPattern]
            except KeyError:
                pass
        else:
            # Wildcard
            for ref, oid in self.refs.items():
                if ref.startswith(refPattern):
                    yield oid

    def newHiddenCommitSolver(self) -> GraphTrickle:
        trickle = GraphTrickle()

        # Explicitly show all refs by default
        for head in self.refs.values():
            trickle.setEnd(head)

        # Explicitly hide tips
        for hiddenBranchTip in self.getHiddenTips():
            trickle.setPipe(hiddenBranchTip)

        """
        # Explicitly hide stash junk parents
        if settings.prefs.hideStashJunkParents:
            for stash in self.repo.listall_stashes():
                stashCommit = self.repo.peel_commit(stash.commit_id)
                for i, parent in enumerate(stashCommit.parent_ids):
                    if i > 0:
                        trickle.setTap(parent)
        """

        return trickle

    @benchmark
    def resolveHiddenCommits(self):
        self.hiddenCommits = set()
        solver = self.newHiddenCommitSolver()
        for i, commit in enumerate(self.commitSequence):
            if not commit:  # May be a fake commit such as Uncommitted Changes
                continue
            solver.newCommit(commit.id, commit.parent_ids, self.hiddenCommits)
            # Don't check if trickle is complete too often (expensive)
            if (i % 250 == 0) and solver.done:
                logger.debug(f"resolveHiddenCommits complete in {i} iterations")
                break

    def newForeignCommitSolver(self) -> GraphTrickle:
        trickle = GraphTrickle()

        for oid, refList in self.refsByOid.items():
            assert oid not in trickle.frontier
            isLocal = any(name == 'HEAD' or name.startswith("refs/heads/") for name in refList)
            if isLocal:
                trickle.setEnd(oid)
            else:
                trickle.setPipe(oid)

        return trickle
