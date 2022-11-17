from collections import defaultdict
from gitfourchette import log
from pygit2 import Commit, Diff, Oid, Repository, Signature
import pygit2
import os
import re


CORE_STASH_MESSAGE_PATTERN = re.compile(r"^On [^\s:]+: (.+)")


class DivergentBranchesError(Exception):
    def __init__(self, localBranch: pygit2.Branch, remoteBranch: pygit2.Branch):
        super().__init__()
        self.localBranch = localBranch
        self.remoteBranch = remoteBranch

    def __str__(self):
        return f"DivergentBranchesError(local: {self.localBranch.shorthand}, remote: {self.remoteBranch.shorthand})"


class ConflictError(Exception):
    def __init__(self, conflicts: list[str], description="Conflicts"):
        super().__init__(description)
        self.description = description
        self.conflicts = conflicts

    def __str__(self):
        return f"ConflictError({len(self.conflicts)}, {self.description})"


class CheckoutTraceCallbacks(pygit2.CheckoutCallbacks):
    status: dict[str, int]

    def __init__(self):
        super().__init__()
        self.status = dict()

    def checkout_notify(self, why: int, path: str, baseline=None, target=None, workdir=None):
        self.status[path] = why

    def get_conflicts(self):
        return [path for path in self.status
                if self.status[path] == pygit2.GIT_CHECKOUT_NOTIFY_CONFLICT]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not exc_type:
            return False
        if issubclass(exc_type, pygit2.GitError):
            message = str(exc_val)
            if "prevents checkout" in message or "prevent checkout" in message:
                conflicts = self.get_conflicts()
                if conflicts:
                    raise ConflictError(conflicts, "workdir")
        return False  # let error propagate


class StashApplyTraceCallbacks(pygit2.StashApplyCallbacks, CheckoutTraceCallbacks):
    def stash_apply_progress(self, pr):
        log.info("porcelain", f"stash apply progress: {pr}")


def refreshIndex(repo: Repository):
    """
    Reload the index. Call this before manipulating the staging area
    to ensure any external modifications are taken into account.

    This is a fairly cheap operation if the index hasn't changed on disk.
    """
    repo.index.read()


def diffWorkdirToIndex(repo: Repository, updateIndex: bool) -> Diff:
    flags = (pygit2.GIT_DIFF_INCLUDE_UNTRACKED
             | pygit2.GIT_DIFF_RECURSE_UNTRACKED_DIRS
             | pygit2.GIT_DIFF_SHOW_UNTRACKED_CONTENT
             )

    # GIT_DIFF_UPDATE_INDEX may improve performance for subsequent diffs if the
    # index was stale, but this requires the repo to be writable.
    if updateIndex:
        log.info("porcelain", "GIT_DIFF_UPDATE_INDEX")
        flags |= pygit2.GIT_DIFF_UPDATE_INDEX

    dirtyDiff = repo.diff(None, None, flags=flags)
    dirtyDiff.find_similar()
    return dirtyDiff


def diffIndexToHead(repo: Repository, fast=False) -> Diff:
    if repo.head_is_unborn:  # can't compare against HEAD (empty repo or branch pointing nowhere)
        indexTreeOid = repo.index.write_tree()
        tree: pygit2.Tree = repo[indexTreeOid].peel(pygit2.Tree)
        return tree.diff_to_tree(swap=True)
    else:
        stageDiff: Diff = repo.diff('HEAD', None, cached=True)  # compare HEAD to index
        if not fast:
            stageDiff.find_similar()
        return stageDiff


def hasAnyStagedChanges(repo: Repository) -> bool:
    return 0 != len(diffIndexToHead(repo, fast=True))
    """
    # This also works, but it's kinda slow...
    status = repo.status(untracked_files="no")
    mask = (pygit2.GIT_STATUS_INDEX_NEW
            | pygit2.GIT_STATUS_INDEX_MODIFIED
            | pygit2.GIT_STATUS_INDEX_DELETED
            | pygit2.GIT_STATUS_INDEX_RENAMED
            | pygit2.GIT_STATUS_INDEX_TYPECHANGE)
    return any(0 != (flag & mask) for flag in status.values())
    """


def loadCommitDiffs(repo: Repository, oid: Oid) -> list[Diff]:
    commit: pygit2.Commit = repo.get(oid)
    #import time; time.sleep(1) #to debug out-of-order events

    if commit.parents:
        allDiffs = []
        for parent in commit.parents:
            diff = repo.diff(parent, commit)
            diff.find_similar()
            allDiffs.append(diff)
        return allDiffs

    else:  # parentless commit
        tree: pygit2.Tree = commit.peel(pygit2.Tree)
        diff = tree.diff_to_tree(swap=True)
        return [diff]


def checkoutLocalBranch(repo: Repository, localBranchName: str):
    branch = repo.branches.local[localBranchName]
    with CheckoutTraceCallbacks() as callbacks:
        repo.checkout(branch.raw_name, callbacks=callbacks)


def checkoutRef(repo: Repository, refName: str):
    with CheckoutTraceCallbacks() as callbacks:
        repo.checkout(refName, callbacks=callbacks)


def checkoutCommit(repo: pygit2.Repository, commitOid: pygit2.Oid):
    commit: pygit2.Commit = repo[commitOid].peel(pygit2.Commit)
    with CheckoutTraceCallbacks() as callbacks:
        repo.checkout_tree(commit.tree, callbacks=callbacks)
        repo.set_head(commitOid)


def revertCommit(repo: pygit2.Repository, commitOid: pygit2.Oid):
    trashCommit = repo[commitOid].peel(pygit2.Commit)
    headCommit = getHeadCommit(repo)
    revertIndex = repo.revert_commit(trashCommit, headCommit)

    if revertIndex.conflicts:
        earlyConflicts = []
        for commonAncestor, ours, theirs in revertIndex.conflicts:
            # Figure out a path to display (note that elements of the 3-tuple may be None!)
            for candidate in [commonAncestor, ours, theirs]:
                if candidate and candidate.path:
                    earlyConflicts.append(candidate.path)
                    break
        raise ConflictError(earlyConflicts, "HEAD")

    with CheckoutTraceCallbacks() as callbacks:
        repo.checkout_index(revertIndex, callbacks=callbacks)


def renameBranch(repo: Repository, oldName: str, newName: str):
    # TODO: if the branch tracks an upstream branch, issue a warning that it won't be renamed on the server
    branch = repo.branches.local[oldName]
    branch.rename(newName)


def deleteBranch(repo: Repository, localBranchName: str):
    # TODO: if remote-tracking, let user delete upstream too?
    repo.branches.local.delete(localBranchName)


def newBranch(repo: Repository, localBranchName: str) -> pygit2.Branch:
    return repo.create_branch(localBranchName, getHeadCommit(repo))


def newTrackingBranch(repo: Repository, localBranchName: str, remoteBranchName: str) -> pygit2.Branch:
    remoteBranch = repo.branches.remote[remoteBranchName]
    commit: pygit2.Commit = remoteBranch.peel(pygit2.Commit)
    branch = repo.create_branch(localBranchName, commit)
    branch.upstream = remoteBranch
    return branch


def newBranchFromCommit(repo: Repository, localBranchName: str, commitOid: Oid, switchTo: bool):
    commit: Commit = repo[commitOid].peel(Commit)
    branch = repo.create_branch(localBranchName, commit)
    if switchTo:
        checkoutRef(repo, branch.name)  # branch.name is inherited from Reference


def getRemoteBranchNames(repo: Repository) -> dict[str, list[str]]:
    nameDict = defaultdict(list)

    for name in repo.branches.remote:
        if name.endswith("/HEAD"):
            # Skip refs/remotes/*/HEAD (the remote's default branch).
            # The ref file (.git/refs/remotes/*/HEAD) is created ONCE when first cloning the repository,
            # and it's never updated again automatically, even if the default branch has changed on the remote.
            # It's a symbolic branch, so looking up a stale version of the remote's HEAD may raise KeyError.
            # It's just not worth the trouble.
            # See: https://stackoverflow.com/questions/8839958
            continue

        try:
            remoteBranch = repo.branches.remote[name]
            remoteName = remoteBranch.remote_name
            strippedBranchName = name.removeprefix(remoteName + "/")
            nameDict[remoteName].append(strippedBranchName)
        except (KeyError, ValueError) as exc:
            # `git svn clone` creates .git/refs/remotes/git-svn, which trips up pygit2
            log.warning("porcelain", exc)

    return nameDict


class BranchNameValidationError(ValueError):
    CANNOT_BE_EMPTY = 0
    ILLEGAL_NAME = 1
    ILLEGAL_PREFIX = 2
    ILLEGAL_SUFFIX = 3
    CONTAINS_ILLEGAL_CHAR = 4
    CONTAINS_ILLEGAL_SEQ = 5

    def __init__(self, code: int):
        super().__init__(F"Branch name validation failed ({code})")
        self.code = code


def validateBranchName(newBranchName: str):
    """
    Checks the validity of a branch name according to `man git-check-ref-format`.
    """

    E = BranchNameValidationError

    if not newBranchName:
        raise E(E.CANNOT_BE_EMPTY)

    # Rule 9: can't be single character '@'
    elif newBranchName == '@':
        raise E(E.ILLEGAL_NAME)

    # Rule 4: forbid space, tilde, caret, colon
    # Rule 5: forbid question mark, asterisk, open bracket
    # Rule 10: forbid backslash
    elif any(c in " ~^:[?*\\" for c in newBranchName):
        raise E(E.CONTAINS_ILLEGAL_CHAR)

    # Rule 1: slash-separated components can't start with dot or end with .lock
    # Rule 3: forbid consecutive dots
    # Rule 6: forbid consecutive slashes
    # Rule 8: forbid '@{'
    elif any(seq in newBranchName for seq in ["/.", ".lock/", "..", "//", "@{"]):
        raise E(E.CONTAINS_ILLEGAL_SEQ)

    # Rule 1: can't start with dot
    # Rule 6: can't start with slash
    elif newBranchName.startswith((".", "/")):
        raise E(E.ILLEGAL_PREFIX)

    # Rule 1: can't end with .lock
    # Rule 6: can't end with slash
    # Rule 7: can't end with dot
    elif newBranchName.endswith((".lock", "/", ".")):
        raise E(E.ILLEGAL_SUFFIX)


def generateUniqueBranchNameOnRemote(repo: pygit2.Repository, remoteName: str, seedBranchName: str):
    """ Generate a name that doesn't clash with any existing branches on the remote """

    i = 1
    newBranchName = seedBranchName
    allRemoteBranches = list(repo.branches.remote)

    while F"{remoteName}/{newBranchName}" in allRemoteBranches:
        i += 1
        newBranchName = F"{seedBranchName}-{i}"

    return newBranchName


def getTagNames(repo: Repository) -> list[str]:
    return [
        name.removeprefix("refs/tags/")
        for name in repo.listall_references()
        if name.startswith("refs/tags/")
    ]


def editTrackingBranch(repo: Repository, localBranchName: str, remoteBranchName: str):
    localBranch = repo.branches.local[localBranchName]
    if remoteBranchName:
        remoteBranch = repo.branches.remote[remoteBranchName]
        localBranch.upstream = remoteBranch
    else:
        if localBranch.upstream is not None:
            localBranch.upstream = None


def newRemote(repo: Repository, name: str, url: str):
    repo.remotes.create(name, url)


def editRemote(repo: Repository, remoteName: str, newName: str, newURL: str):
    repo.remotes.set_url(remoteName, newURL)
    if remoteName != newName:
        repo.remotes.rename(remoteName, newName)  # rename AFTER setting everything else!


def deleteRemote(repo: Repository, remoteName: str):
    repo.remotes.delete(remoteName)


def deleteRemoteBranch(repo: Repository, remoteBranchName: str, remoteCallbacks: pygit2.RemoteCallbacks):
    remoteName, branchName = splitRemoteBranchShorthand(remoteBranchName)

    refspec = f":refs/heads/{branchName}"
    log.info("porcelain", f"Delete remote branch: refspec: \"{refspec}\"")

    remote = repo.remotes[remoteName]
    remote.push([refspec], callbacks=remoteCallbacks)


def renameRemoteBranch(repo: Repository, oldRemoteBranchName: str, newBranchName: str, remoteCallbacks: pygit2.RemoteCallbacks):
    """
    Warning: this function does not refresh the state of the remote branch before renaming it!
    """
    remoteName, oldBranchName = splitRemoteBranchShorthand(oldRemoteBranchName)

    # First, make a new branch pointing to the same ref as the old one
    refspec1 = f"refs/remotes/{oldRemoteBranchName}:refs/heads/{newBranchName}"

    # Next, delete the old branch
    refspec2 = f":refs/heads/{oldBranchName}"

    log.info("porcelain", f"Rename remote branch: remote: {remoteName}; refspec: {[refspec1, refspec2]}")

    remote = repo.remotes[remoteName]
    remote.push([refspec1, refspec2], callbacks=remoteCallbacks)


def deleteStaleRemoteHEADSymbolicRef(repo: Repository, remoteName: str):
    """
    Delete `refs/remotes/{remoteName}/HEAD` to work around a bug in libgit2
    where `git_revwalk__push_glob` errors out on that symbolic ref
    if it points to a branch that doesn't exist anymore.

    This bug may prevent fetching.
    """

    HEADRefName = F"refs/remotes/{remoteName}/HEAD"
    HEADRef = repo.references.get(HEADRefName)

    # Only risk deleting remote HEAD if it's symbolic
    if HEADRef and HEADRef.type == pygit2.GIT_REF_SYMBOLIC:
        try:
            HEADRef.resolve()
        except KeyError:  # pygit2 wraps GIT_ENOTFOUND with KeyError
            # Stale -- nuke it
            repo.references.delete(HEADRefName)
            log.info("porcelain", "Deleted stale remote HEAD symbolic ref: " + HEADRefName)


def fetchRemote(repo: Repository, remoteName: str, remoteCallbacks: pygit2.RemoteCallbacks) -> pygit2.remote.TransferProgress:
    # Delete `refs/remotes/{remoteName}/HEAD` before fetching.
    # See docstring for that function for why.
    deleteStaleRemoteHEADSymbolicRef(repo, remoteName)

    remote = repo.remotes[remoteName]
    transfer = remote.fetch(callbacks=remoteCallbacks, prune=pygit2.GIT_FETCH_PRUNE)
    return transfer


def splitRemoteBranchShorthand(remoteBranchName: str):
    if remoteBranchName.startswith("refs/"):
        raise ValueError("splitRemoteBranchName: remote branch shorthand name mustn't start with refs/")

    # TODO: extraction of branch name is flaky if remote name or branch name contains slashes
    remoteName, branchName = remoteBranchName.split("/", 1)
    return remoteName, branchName


def fetchRemoteBranch(repo: Repository, remoteBranchName: str, remoteCallbacks: pygit2.RemoteCallbacks) -> pygit2.remote.TransferProgress:
    remoteName, branchName = splitRemoteBranchShorthand(remoteBranchName)

    # Delete .git/refs/{remoteName}/HEAD to work around a bug in libgit2
    # where git_revwalk__push_glob chokes on refs/remotes/{remoteName}/HEAD
    # if it points to a branch that doesn't exist anymore.
    deleteStaleRemoteHEADSymbolicRef(repo, remoteName)

    remote = repo.remotes[remoteName]
    transfer = remote.fetch(refspecs=[branchName], callbacks=remoteCallbacks, prune=pygit2.GIT_FETCH_NO_PRUNE)
    return transfer


def resetHead(repo: Repository, onto: Oid, resetMode: str, recurseSubmodules: bool=False):
    modes = {
        "soft": pygit2.GIT_RESET_SOFT,
        "mixed": pygit2.GIT_RESET_MIXED,
        "hard": pygit2.GIT_RESET_HARD,
    }
    repo.reset(onto, modes[resetMode])
    if recurseSubmodules:
        raise NotImplementedError("reset HEAD + recurse submodules not implemented yet!")


def getHeadCommit(repo: Repository) -> Commit:
    return repo.head.peel(Commit)


def getHeadCommitOid(repo: Repository) -> Oid:
    return getHeadCommit(repo).oid


def getHeadCommitMessage(repo: Repository) -> str:
    return getHeadCommit(repo).message


def getCommitMessage(repo: Repository, oid: Oid) -> str:
    commit: Commit = repo[oid].peel(Commit)
    return commit.message


def createCommit(
        repo: Repository,
        message: str,
        overrideAuthor: Signature | None = None,
        overrideCommitter: Signature | None = None
) -> Oid:
    # Get the ref name pointed to by HEAD, but DON'T use repo.head! It won't work if HEAD is unborn.
    # Both git and libgit2 store a default branch name in .git/HEAD when they init a repo,
    # so we should always have a ref name, even though it might not point to anything.
    refName = repo.lookup_reference("HEAD").target

    if repo.head_is_unborn:
        parents = []
    else:
        parents = [getHeadCommitOid(repo)]

    indexTreeOid = repo.index.write_tree()
    fallbackSignature = repo.default_signature

    newCommitOid = repo.create_commit(
        refName,
        overrideAuthor or fallbackSignature,
        overrideCommitter or fallbackSignature,
        message,
        indexTreeOid,
        parents
    )

    assert not repo.head_is_unborn, "HEAD is still unborn after we have committed!"

    return newCommitOid


def amendCommit(
        repo: Repository,
        message: str,
        overrideAuthor: Signature | None = None,
        overrideCommitter: Signature | None = None
) -> Oid:
    indexTreeOid = repo.index.write_tree(repo)
    newCommitOid = repo.amend_commit(
        getHeadCommit(repo),
        'HEAD',
        message=message,
        author=overrideAuthor,
        committer=overrideCommitter or repo.default_signature,
        tree=indexTreeOid
    )
    return newCommitOid


def getActiveBranchFullName(repo: Repository) -> str:
    return repo.head.name


def getActiveBranchShorthand(repo: Repository) -> str:
    return repo.head.shorthand


def getCommitOidFromReferenceName(repo: Repository, refName: str) -> Oid:
    reference = repo.references[refName]
    commit: Commit = reference.peel(Commit)
    return commit.oid


def getCommitOidFromTagName(repo: Repository, tagName: str) -> Oid:
    raise NotImplementedError("getCommitOidFromTagName")
    # tag: git.Tag = next(filter(lambda tag: tag.name == tagName, repo.tags))
    # return tag.commit.hexsha


def getOidsForAllReferences(repo: Repository) -> list[Oid]:
    """
    Return commit oids at the tip of all branches, tags, etc. in the repository.

    To ensure a consistent outcome across multiple walks of the same commit graph,
    the oids are sorted by descending commit time.
    """
    tips = []
    for ref in repo.listall_reference_objects():
        if type(ref.target) != Oid:
            # Skip symbolic reference
            continue
        if ref.name == "refs/stash":
            continue
        try:
            commit: Commit = ref.peel(Commit)
            tips.append(commit)
        except pygit2.InvalidSpecError as e:
            # Some refs might not be committish, e.g. in linux's source repo
            log.info("porcelain", F"{e} - Skipping ref '{ref.name}'")
            pass

    for stash in repo.listall_stashes():
        try:
            commit: Commit = repo[stash.commit_id].peel(pygit2.Commit)
            tips.append(commit)
        except pygit2.InvalidSpecError as e:
            log.info("porcelain", F"{e} - Skipping stash '{stash.message}'")
            pass

    tips = sorted(tips, key=lambda commit: commit.commit_time, reverse=True)
    return [commit.oid for commit in tips]


def mapCommitsToReferences(repo: pygit2.Repository) -> dict[pygit2.Oid, list[str]]:
    commit2refs = defaultdict(list)

    for ref in repo.references.objects:
        refKey = ref.name

        if type(ref.target) != pygit2.Oid:
            log.info("porcelain", F"Skipping symbolic reference {refKey} --> {ref.target}")
            continue

        assert refKey.startswith("refs/")
        if refKey == "refs/stash":
            continue
        commit2refs[ref.target].append(refKey)

    for stashIndex, stash in enumerate(repo.listall_stashes()):
        commit2refs[stash.commit_id].append(F"stash@{{{stashIndex}}}")

    return commit2refs


def stageFiles(repo: Repository, patches: list[pygit2.Patch]):
    index = repo.index
    for patch in patches:
        if patch.delta.status == pygit2.GIT_DELTA_DELETED:
            index.remove(patch.delta.new_file.path)
        else:
            index.add(patch.delta.new_file.path)
    index.write()


def discardFiles(repo: Repository, paths: list[str]):
    """
    Discards unstaged changes in the given files.
    Does not discard any changes that are staged.
    """

    strategy = (pygit2.GIT_CHECKOUT_FORCE
                | pygit2.GIT_CHECKOUT_REMOVE_UNTRACKED
                | pygit2.GIT_CHECKOUT_DONT_UPDATE_INDEX  # not strictly necessary, but prevents nuking staged changes inadvertently
                | pygit2.GIT_CHECKOUT_DISABLE_PATHSPEC_MATCH)

    # refresh index before getting indexTree in case an external program modified the staging area
    repo.index.read()

    # get tree with staged changes
    indexTreeId = repo.index.write_tree()
    indexTree = repo[indexTreeId]

    # reset files to their state in the staged tree
    repo.checkout_tree(indexTree, paths=paths, strategy=strategy)


def unstageFiles(repo: Repository, patches: list[pygit2.Patch]):
    index = repo.index

    headTree: pygit2.Tree | None
    if repo.head_is_unborn:
        headTree = None
    else:
        headTree = repo.head.peel(pygit2.Tree)

    for patch in patches:
        delta = patch.delta
        old_path = delta.old_file.path
        new_path = delta.new_file.path
        if delta.status == pygit2.GIT_DELTA_ADDED:
            assert (not headTree) or (old_path not in headTree)
            index.remove(old_path)
        elif delta.status == pygit2.GIT_DELTA_RENAMED:
            # TODO: Two-step removal to completely unstage a rename -- is this what we want?
            assert new_path in index
            index.remove(new_path)
        else:
            assert headTree
            assert old_path in headTree
            obj = headTree[old_path]
            index.add(pygit2.IndexEntry(old_path, obj.oid, obj.filemode))
    index.write()


def newStash(repo: Repository, message: str, flags: str) -> pygit2.Oid:
    oid = repo.stash(
        stasher=repo.default_signature,
        message=message,
        keep_index='k' in flags,
        include_untracked='u' in flags,
        include_ignored='i' in flags)
    return oid


def findStashIndex(repo: Repository, commitOid: pygit2.Oid):
    """
    Libgit2 takes an index number to apply/pop/drop stashes. However, it's
    unsafe to cache such an index for the GUI. Instead, we cache the commit ID
    of the stash, and we only convert that to an index when we need to perform
    an operation on the stash. This way, we'll always manipulate the stash
    intended by the user, even if the indices change outside our control.
    """
    return next(i
                for i, stash in enumerate(repo.listall_stashes())
                if stash.commit_id == commitOid)


def applyStash(repo: Repository, commitId: pygit2.Oid):
    with StashApplyTraceCallbacks() as callbacks:
        repo.stash_apply(findStashIndex(repo, commitId), callbacks=callbacks)


def popStash(repo: Repository, commitId: pygit2.Oid):
    with StashApplyTraceCallbacks() as callbacks:
        repo.stash_pop(findStashIndex(repo, commitId), callbacks=callbacks)


def dropStash(repo: Repository, commitId: pygit2.Oid):
    repo.stash_drop(findStashIndex(repo, commitId))


def getCoreStashMessage(stashMessage: str):
    m = CORE_STASH_MESSAGE_PATTERN.match(stashMessage)
    if m:
        return m.group(1)
    else:
        return stashMessage


def patchApplies(
        repo: pygit2.Repository,
        patchData: bytes | str,
        location: int = pygit2.GIT_APPLY_LOCATION_WORKDIR
) -> pygit2.Diff:
    diff = pygit2.Diff.parse_diff(patchData)
    repo.applies(diff, location, raise_error=True)
    return diff


def loadPatch(patchDataOrDiff: bytes | str | pygit2.Diff) -> pygit2.Diff:
    if type(patchDataOrDiff) in [bytes, str]:
        return pygit2.Diff.parse_diff(patchDataOrDiff)
    elif type(patchDataOrDiff) is pygit2.Diff:
        return patchDataOrDiff
    else:
        raise TypeError("patchDataOrDiff must be bytes, str, or Diff")
    return diff


def applyPatch(
        repo: pygit2.Repository,
        patchDataOrDiff: bytes | str | pygit2.Diff,
        location: int = pygit2.GIT_APPLY_LOCATION_WORKDIR
) -> pygit2.Diff:
    if type(patchDataOrDiff) in [bytes, str]:
        diff = pygit2.Diff.parse_diff(patchDataOrDiff)
    elif type(patchDataOrDiff) is pygit2.Diff:
        diff = patchDataOrDiff
    else:
        raise TypeError("patchDataOrDiff must be bytes, str, or Diff")

    repo.apply(diff, location)
    return diff


def getSubmoduleWorkdir(repo: pygit2.Repository, submoduleKey: str):
    submo = repo.lookup_submodule(submoduleKey)
    return os.path.join(repo.workdir, submo.path)


def pull(repo: pygit2.Repository, localBranchName: str, remoteBranchName: str):
    lb = repo.branches.local[localBranchName]
    rb = repo.branches.remote[remoteBranchName]

    mergeAnalysis, mergePref = repo.merge_analysis(rb.target, "refs/heads/" + localBranchName)

    mergePrefNames = {
        pygit2.GIT_MERGE_PREFERENCE_NONE: "none",
        pygit2.GIT_MERGE_PREFERENCE_FASTFORWARD_ONLY: "ff only",
        pygit2.GIT_MERGE_PREFERENCE_NO_FASTFORWARD: "no ff"
    }
    log.info("porcelain", f"Merge analysis: {mergeAnalysis}. Merge preference: {mergePrefNames.get(mergePref, '???')}.")

    if mergeAnalysis & pygit2.GIT_MERGE_ANALYSIS_UP_TO_DATE:
        # Local branch is up to date with remote branch, nothing to do.
        return

    elif mergeAnalysis == (pygit2.GIT_MERGE_ANALYSIS_NORMAL | pygit2.GIT_MERGE_ANALYSIS_FASTFORWARD):
        # Go ahead and fast-forward.

        # First, we need to check out the tree pointed to by the remote branch. This step is necessary,
        # otherwise the contents of the commits we're pulling will spill into the unstaged area.
        # Note: checkout_tree defaults to a safe checkout, so it'll raise GitError if any uncommitted changes
        # affect any of the files that are involved in the pull.
        with CheckoutTraceCallbacks() as callbacks:
            repo.checkout_tree(rb.peel(pygit2.Tree), callbacks=callbacks)

        # Then make the local branch point to the same commit as the remote branch.
        lb.set_target(rb.target)

    elif mergeAnalysis == pygit2.GIT_MERGE_ANALYSIS_NORMAL:
        # Can't FF. Divergent branches?
        raise DivergentBranchesError(lb, rb)

    else:
        # Unborn or something...
        raise NotImplementedError(F"Unsupported merge analysis {mergeAnalysis}.")


def getSuperproject(repo: pygit2.Repository):
    """
    If `repo` is a submodule, returns the path to the superproject's working directory,
    otherwise returns None.
    Equivalent to `git rev-parse --show-superproject-working-tree`.
    """

    repoPath = repo.path  # e.g. "/home/user/superproj/.git/modules/src/extern/subproj/"
    gitModules = "/.git/modules/"
    gitModulesPos = repoPath.rfind(gitModules)

    if gitModulesPos >= 0:
        superWD = repoPath[:gitModulesPos]  # e.g. "/home/user/superproj"
        subWDRelative = repoPath[gitModulesPos + len(gitModules):]  # e.g. "src/extern/subproj/"

        # Recompose full path to submodule workdir to ensure we are indeed a submodule of the tentative superproject
        subWD = superWD + "/" + subWDRelative  # e.g. "/home/user/superproj/src/extern/subproj/"
        if subWD == repo.workdir:
            return superWD

    return None

