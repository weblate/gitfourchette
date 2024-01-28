import logging
import os
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable

from gitfourchette import settings
from gitfourchette import tempdir
from gitfourchette.graph import Graph, GraphSplicer
from gitfourchette.graphmarkers import HiddenCommitSolver, ForeignCommitSolver
from gitfourchette.porcelain import *
from gitfourchette.prefsfile import PrefsFile
from gitfourchette.qt import *
from gitfourchette.toolbox import *

logger = logging.getLogger(__name__)

UC_FAKEID = "UC_FAKEID"
PROGRESS_INTERVAL = 5000


def toggleListElement(l: list, e):
    assert isinstance(l, list)
    try:
        l.remove(e)
        return False
    except ValueError:
        l.append(e)
        return True


@dataclass
class RepoPrefs(PrefsFile):
    _filename = f"{APP_SYSTEM_NAME}.json"
    _allowMakeDirs = False
    _parentDir = ""

    draftCommitMessage: str = ""
    draftCommitSignature: Signature = None
    draftAmendMessage: str = ""
    hiddenBranches: list = field(default_factory=list)
    hiddenStashCommits: list = field(default_factory=list)
    hiddenRemotes: list = field(default_factory=list)
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

        # On Windows, core.autocrlf is usually set to true in the system config.
        # However, libgit2 cannot find the system config if git wasn't installed
        # with the official installer, e.g. via scoop. If a repo was cloned with
        # autocrlf=true, GF's staging area would be unusable on Windows without
        # setting autocrlf=true in the config.
        if WINDOWS and "core.autocrlf" not in self.repo.config:
            tempConfigPath = os.path.join(tempdir.getSessionTemporaryDirectory(), "gitconfig")
            logger.info(f"Forcing core.autocrlf=true in: {tempConfigPath}")
            tempConfig = GitConfig(tempConfigPath)
            tempConfig["core.autocrlf"] = "true"
            self.repo.config.add_file(tempConfigPath, level=1)

        self.walker = None

        self.commitSequence = []
        self.hiddenCommits = set()

        self.graph = None
        self.localCommits = None

        self.headIsDetached = False
        self.homeBranch = ""
        self.refCache = {}
        self.reverseRefCache = {}
        self.mergeheadsCache = []

        self.refreshRefCache()
        self.refreshMergeheadsCache()

        self.superproject = repo.get_superproject()

        self.activeCommitOid = None

        self.workdirStale = True
        self.numUncommittedChanges = 0

        self.uiPrefs.load()

        self.resolveHiddenCommits()

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

        if self.repo.head_is_detached or self.repo.head_is_unborn:
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

        if settings.prefs.graph_chronologicalOrder:
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

    @benchmark
    def loadChangedRefs(self, oldRefCache: dict[str, Oid]):
        # DO NOT call processEvents() here. While splicing a large amount of
        # commits, GraphView may try to repaint an incomplete graph.
        # GraphView somehow ignores setUpdatesEnabled(False) here!

        newCommitSequence = []

        oldHeads = oldRefCache.values()
        newHeads = self.refCache.values()

        graphSplicer = GraphSplicer(self.graph, oldHeads, newHeads)
        newHiddenCommitSolver: HiddenCommitSolver = self.newHiddenCommitSolver()
        newForeignCommitSolver = ForeignCommitSolver(self.reverseRefCache)

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
    def toggleHideBranch(self, branchName: str):
        toggleListElement(self.uiPrefs.hiddenBranches, branchName)
        self.uiPrefs.write()
        self.resolveHiddenCommits()

    @benchmark
    def toggleHideStash(self, stashOid: Oid):
        toggleListElement(self.uiPrefs.hiddenStashCommits, stashOid.hex)
        self.uiPrefs.write()
        self.resolveHiddenCommits()

    @benchmark
    def toggleHideAllStashes(self):
        self.uiPrefs.hideAllStashes = not self.uiPrefs.hideAllStashes
        self.uiPrefs.write()
        self.resolveHiddenCommits()

    @benchmark
    def toggleHideRemote(self, remoteName: str):
        toggleListElement(self.uiPrefs.hiddenRemotes, remoteName)
        self.uiPrefs.write()
        self.resolveHiddenCommits()

    def getHiddenBranchOids(self):
        seeds = set()
        hiddenBranches = self.uiPrefs.hiddenBranches[:]

        if self.uiPrefs.hiddenRemotes:
            for refName, oid in self.refCache.items():
                prefix, name = RefPrefix.split(refName)
                if prefix == RefPrefix.REMOTES:
                    remoteName = name.split('/', 1)[0]
                    if remoteName in self.uiPrefs.hiddenRemotes:
                        hiddenBranches.append(refName)

        def isSharedByVisibleBranch(oid):
            return any(
                refName for refName in self.reverseRefCache[oid]
                if refName not in hiddenBranches
                and not refName.startswith(RefPrefix.TAGS))

        for hiddenBranch in hiddenBranches:
            try:
                oid = self.refCache[hiddenBranch]
                if not isSharedByVisibleBranch(oid):
                    seeds.add(oid)
            except (KeyError, InvalidSpecError):
                # Remove it from prefs
                logger.info(f"Skipping missing hidden branch: {hiddenBranch}")
                self.uiPrefs.hiddenBranches.remove(hiddenBranch)

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

    def newHiddenCommitSolver(self) -> HiddenCommitSolver:
        solver = HiddenCommitSolver()
        T = HiddenCommitSolver.Tag

        for head in self.refCache.values():
            solver.tagCommit(head, T.SHOW)

        for hiddenBranchTip in self.getHiddenBranchOids():
            solver.tagCommit(hiddenBranchTip, T.SOFTHIDE)

        if settings.prefs.debug_hideStashJunkParents:
            for stash in self.repo.listall_stashes():
                stashCommit = self.repo.peel_commit(stash.commit_id)
                if len(stashCommit.parents) >= 2 and stashCommit.parents[1].raw_message.startswith(b"index on "):
                    solver.tagCommit(stashCommit.parents[1].id, T.HARDHIDE)
                if len(stashCommit.parents) >= 3 and stashCommit.parents[2].raw_message.startswith(b"untracked files on "):
                    solver.tagCommit(stashCommit.parents[2].id, T.HARDHIDE)

        return solver

    def resolveHiddenCommits(self):
        self.hiddenCommits = set()
        solver = self.newHiddenCommitSolver()
        for commit in self.commitSequence:
            if not commit:  # May be a fake commit such as Uncommitted Changes
                continue
            solver.newCommit(commit.oid, commit.parent_ids, self.hiddenCommits)
            if solver.done:
                break
