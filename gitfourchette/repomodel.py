import logging
from collections import defaultdict
from typing import Generator

from gitfourchette import settings
from gitfourchette.graph import Graph, GraphSplicer, GraphTrickle
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
    "Get target commit ID by reference name."

    refsAt: dict[Oid, list[str]]
    "Get all reference names pointing at a given commit ID."

    mergeheads: list[Oid]

    stashes: list[Oid]

    submodules: dict[str, str]

    superproject: str
    "Path of the superproject. Empty string if this isn't a submodule."

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
        self.homeBranch = ""

        self.superproject = ""
        self.workdirStale = True
        self.numUncommittedChanges = 0

        self.refs = {}
        self.refsAt = {}
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

    @property
    def headCommitId(self) -> Oid:
        """ Oid of the currently checked-out commit. """
        try:
            return self.refs["HEAD"]
        except GitError:
            return NULL_OID

    @benchmark
    def syncRefs(self):
        """ Refresh cached refs (`refs` and `refsAt`).

        Return True if there were any changes in the refs since the last
        refresh, or False if nothing changed.
        """

        headWasDetached = self.headIsDetached
        self.headIsDetached = self.repo.head_is_detached

        if self.headIsDetached or self.repo.head_is_unborn:
            self.homeBranch = ""
        else:
            self.homeBranch = self.repo.head_branch_shorthand

        refs = self.repo.map_refs_to_ids(include_stashes=False)

        if refs == self.refs:
            # Make sure it's sorted in the exact same order...
            if settings.DEVDEBUG:
                assert list(refs.keys()) == list(self.refs.keys()), "refs key order changed! how did that happen?"

            # Nothing to do!
            # Still, signal a change if HEAD just detached/reattached.
            return headWasDetached != self.headIsDetached

        # Build reverse ref cache
        refsAt = defaultdict(list)
        for k, v in refs.items():
            refsAt[v].append(k)

        # Special case for HEAD: Make it appear first in reverse ref cache
        try:
            headId = refs["HEAD"]
            refsAt[headId].remove("HEAD")
            refsAt[headId].insert(0, "HEAD")
        except KeyError:
            pass

        # Store new cache
        self.refs = refs
        self.refsAt = refsAt

        # Since the refs have changed, we need to refresh hidden refs
        self.refreshHiddenRefCache()

        # Let caller know that the refs changed.
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
            headTips = self.refsAt[self.headCommitId]
        except KeyError:
            return False

        if headTips != ["HEAD"]:
            return False

        try:
            frame = self.graph.getCommitFrame(self.headCommitId)
        except KeyError:
            # Head commit not in graph, cannot determine if dangerous, err on side of caution
            return True

        arcs = list(frame.arcsClosedByCommit())

        if len(arcs) == 0:
            return True

        if len(arcs) != 1:
            return False

        return arcs[0].openedBy == UC_FAKEID

    @benchmark
    def syncTopOfGraph(self, oldRefs: dict[str, Oid]) -> tuple[int, int]:
        # DO NOT call processEvents() here. While splicing a large amount of
        # commits, GraphView may try to repaint an incomplete graph.
        # GraphView somehow ignores setUpdatesEnabled(False) here!

        newCommitSequence = []

        oldHeads = oldRefs.values()
        newHeads = self.refs.values()

        graphSplicer = GraphSplicer(self.graph, oldHeads, newHeads)
        hiddenTrickle = self.newHiddenCommitTrickle()
        foreignTrickle = self.newForeignCommitTrickle()

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

                    hiddenTrickle.newCommit(oid, parents, self.hiddenCommits, discard=True)
                    foreignTrickle.newCommit(oid, parents, self.foreignCommits, discard=True)

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

        # Finish patching hidden/foreign commit sets.
        # Keep feeding commits to trickle until it stabilizes to its previous state.
        if graphSplicer.foundEquilibrium:
            with Benchmark("Finish patching hidden/foreign commits"):
                row = nAdded + 1
                r1 = self._stabilizeTrickle(hiddenTrickle, self.hiddenCommits, row)
                r2 = self._stabilizeTrickle(foreignTrickle, self.foreignCommits, row)
                logger.debug(f"Trickle stabilization: Hidden={r1}; Foreign={r2}")

        return nRemoved, nAdded

    def _stabilizeTrickle(self, trickle: GraphTrickle, flaggedSet: set[Oid], startRow: int):
        if trickle.done:
            return startRow

        for row in range(startRow, len(self.commitSequence)):
            commit = self.commitSequence[row]

            wasFlagged = commit.id in flaggedSet
            isFlagged = trickle.newCommit(commit.id, commit.parent_ids, flaggedSet, discard=True)

            trickleEquilibrium = (wasFlagged == isFlagged)
            if trickleEquilibrium or trickle.done:
                return row

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
                ref for ref in self.refsAt[oid]
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

    @benchmark
    def resolveHiddenCommits(self):
        self.hiddenCommits = set()
        trickle = self.newHiddenCommitTrickle()
        for i, commit in enumerate(self.commitSequence):
            if not commit:  # May be a fake commit such as Uncommitted Changes
                continue
            trickle.newCommit(commit.id, commit.parent_ids, self.hiddenCommits)
            # Don't check if trickle is complete too often (expensive)
            if (i % 250 == 0) and trickle.done:
                logger.debug(f"resolveHiddenCommits complete in {i} iterations")
                break

    def newHiddenCommitTrickle(self) -> GraphTrickle:
        return GraphTrickle.initForHiddenCommits(self.refs.values(), self.getHiddenTips())

    def newForeignCommitTrickle(self) -> GraphTrickle:
        return GraphTrickle.initForForeignCommits(self.refsAt)
