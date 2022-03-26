from collections import defaultdict
from gitfourchette import log
from pygit2 import Commit, Diff, Oid, Repository, Signature
import pygit2
import os


def diffWorkdirToIndex(repo: Repository) -> Diff:
    # GIT_DIFF_UPDATE_INDEX may improve performance for subsequent diffs if the
    # index was stale, but this requires the repo to be writable.
    flags = (pygit2.GIT_DIFF_INCLUDE_UNTRACKED
             | pygit2.GIT_DIFF_RECURSE_UNTRACKED_DIRS
             | pygit2.GIT_DIFF_SHOW_UNTRACKED_CONTENT
             | pygit2.GIT_DIFF_UPDATE_INDEX
             )
    dirtyDiff = repo.diff(None, None, flags=flags)
    dirtyDiff.find_similar()
    return dirtyDiff


def diffIndexToHead(repo: Repository) -> Diff:
    if repo.head_is_unborn:  # can't compare against HEAD (empty repo or branch pointing nowhere)
        indexTreeOid = repo.index.write_tree()
        tree: pygit2.Tree = repo[indexTreeOid].peel(pygit2.Tree)
        return tree.diff_to_tree(swap=True)
    else:
        stageDiff: Diff = repo.diff('HEAD', None, cached=True)  # compare HEAD to index
        stageDiff.find_similar()
        return stageDiff


def hasAnyStagedChanges(repo: Repository) -> bool:
    status = repo.status()
    mask = (pygit2.GIT_STATUS_INDEX_NEW
            | pygit2.GIT_STATUS_INDEX_MODIFIED
            | pygit2.GIT_STATUS_INDEX_DELETED
            | pygit2.GIT_STATUS_INDEX_RENAMED
            | pygit2.GIT_STATUS_INDEX_TYPECHANGE)
    return any(0 != (flag & mask) for flag in status.values())


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
    repo.checkout(branch.raw_name)


def checkoutRef(repo: Repository, refName: str):
    repo.checkout(refName)


def checkoutCommit(repo: pygit2.Repository, commitOid: pygit2.Oid):
    commit: pygit2.Commit = repo[commitOid].peel(pygit2.Commit)
    repo.checkout_tree(commit.tree)
    repo.set_head(commitOid)


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


def newBranchFromCommit(repo: Repository, localBranchName: str, commitOid: Oid):
    commit: Commit = repo[commitOid].peel(Commit)
    branch = repo.create_branch(localBranchName, commit)
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

        remoteBranch = repo.branches.remote[name]
        remoteName = remoteBranch.remote_name
        strippedBranchName = name.removeprefix(remoteName + "/")
        nameDict[remoteName].append(strippedBranchName)

    return nameDict


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


def fetchRemote(repo: Repository, remoteName: str, remoteCallbacks: pygit2.RemoteCallbacks) -> pygit2.remote.TransferProgress:
    tp = repo.remotes[remoteName].fetch(callbacks=remoteCallbacks, prune=pygit2.GIT_FETCH_PRUNE)
    return tp


def fetchRemoteBranch(repo: Repository, remoteBranchName: str, remoteCallbacks: pygit2.RemoteCallbacks) -> pygit2.remote.TransferProgress:
    # TODO: extraction of branch name is flaky if remote name or branch name contains slashes
    remoteName, branchName = remoteBranchName.split("/", 1)
    tp = repo.remotes[remoteName].fetch(refspecs=[branchName], callbacks=remoteCallbacks, prune=pygit2.GIT_FETCH_NO_PRUNE)
    return tp


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

    for refKey in repo.references:
        ref = repo.references[refKey]

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
    repo.stash_apply(findStashIndex(repo, commitId))


def popStash(repo: Repository, commitId: pygit2.Oid):
    repo.stash_pop(findStashIndex(repo, commitId))


def dropStash(repo: Repository, commitId: pygit2.Oid):
    repo.stash_drop(findStashIndex(repo, commitId))


def patchApplies(repo: pygit2.Repository, patchData: bytes | str, discard: bool = False) -> pygit2.Diff | None:
    if discard:
        location = pygit2.GIT_APPLY_LOCATION_WORKDIR
    else:
        location = pygit2.GIT_APPLY_LOCATION_INDEX

    diff = pygit2.Diff.parse_diff(patchData)
    if repo.applies(diff, location):
        return diff
    else:
        return None


def applyPatch(repo: pygit2.Repository, patchDataOrDiff: bytes | str | pygit2.Diff, discard: bool = False) -> pygit2.Diff:
    if discard:
        location = pygit2.GIT_APPLY_LOCATION_WORKDIR
    else:
        location = pygit2.GIT_APPLY_LOCATION_INDEX

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
