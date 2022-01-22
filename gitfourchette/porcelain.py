from collections import defaultdict

from pygit2 import Commit, Diff, Oid, Repository, Signature, Branch
import pygit2


def loadDirtyDiff(repo: Repository) -> Diff:
    flags = pygit2.GIT_DIFF_INCLUDE_UNTRACKED \
          | pygit2.GIT_DIFF_RECURSE_UNTRACKED_DIRS
    dirtyDiff: Diff = repo.diff(None, None, flags=flags)
    dirtyDiff.find_similar()
    return dirtyDiff


def loadStagedDiff(repo: Repository) -> Diff:
    if repo.head_is_unborn:  # can't compare against HEAD (empty repo or branch pointing nowhere)
        indexTreeOid = repo.index.write_tree()
        tree: pygit2.Tree = repo[indexTreeOid].peel(pygit2.Tree)
        return tree.diff_to_tree(swap=True)
    else:
        stageDiff: Diff = repo.diff('HEAD', None, cached=True)  # compare HEAD to index
        stageDiff.find_similar()
        return stageDiff


def hasAnyStagedChanges(repo: Repository) -> bool:
    status: dict[str, int] = repo.status()
    mask \
        = pygit2.GIT_STATUS_INDEX_NEW \
        | pygit2.GIT_STATUS_INDEX_MODIFIED \
        | pygit2.GIT_STATUS_INDEX_DELETED \
        | pygit2.GIT_STATUS_INDEX_RENAMED \
        | pygit2.GIT_STATUS_INDEX_TYPECHANGE
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
    branch: Branch = repo.branches.local[localBranchName]
    repo.checkout(branch.raw_name)


def checkoutRef(repo: Repository, refName: str):
    repo.checkout(refName)


def renameBranch(repo: Repository, oldName: str, newName: str):
    # TODO: if the branch tracks an upstream branch, issue a warning that it won't be renamed on the server
    branch: pygit2.Branch = repo.branches.local[oldName]
    branch.rename(newName)


def deleteBranch(repo: Repository, localBranchName: str):
    # TODO: if remote-tracking, let user delete upstream too?
    repo.branches.local.delete(localBranchName)


def newBranch(repo: Repository, localBranchName: str) -> pygit2.Branch:
    return repo.create_branch(localBranchName, getHeadCommit(repo))


def newTrackingBranch(repo: Repository, localBranchName: str, remoteBranchName: str) -> pygit2.Branch:
    branch = newBranch(repo, localBranchName)
    editTrackingBranch(repo, localBranchName, remoteBranchName)
    return branch


def newBranchFromCommit(repo: Repository, localBranchName: str, commitOid: Oid):
    commit: Commit = repo[commitOid].peel(Commit)
    branch: Branch = repo.create_branch(localBranchName, commit)
    checkoutRef(repo, branch.name)  # branch.name is inherited from Reference


def getRemoteBranchNames(repo: Repository) -> dict[str, list[str]]:
    nameDict = defaultdict(list)

    remoteBranch: Branch
    for name in repo.branches.remote:
        remoteBranch: pygit2.Branch = repo.branches.remote[name]
        remoteName = remoteBranch.remote_name
        strippedBranchName = name.removeprefix(remoteName + "/")
        nameDict[remoteBranch.remote_name].append(strippedBranchName)

    return nameDict


def getTagNames(repo: Repository) -> list[str]:
    return [
        name.removeprefix("refs/tags/")
        for name in repo.listall_references()
        if name.startswith("refs/tags/")
    ]


def editTrackingBranch(repo: Repository, localBranchName: str, remoteBranchName: str):
    localBranch: pygit2.Branch = repo.branches.local[localBranchName]
    if remoteBranchName:
        remoteBranch: pygit2.Branch = repo.branches.remote[remoteBranchName]
        localBranch.upstream = remoteBranch
    else:
        if localBranch.upstream is not None:
            localBranch.upstream = None


def editRemote(repo: Repository, remoteName: str, newName: str, newURL: str):
    repo.remotes.set_url(remoteName, newURL)
    if remoteName != newName:
        repo.remotes.rename(remoteName, newName)  # rename AFTER setting everything else!


def deleteRemote(repo: Repository, remoteName: str):
    repo.remotes.delete(remoteName)


def resetHead(repo: Repository, ontoHexsha: str, resetMode: str, recurseSubmodules: bool):
    raise NotImplementedError("reset HEAD")
    args = ['--' + resetMode]
    if recurseSubmodules:
        args += ['--recurse-submodules']
    else:
        args += ['--no-recurse-submodules']
    args += [ontoHexsha]

    print(*args)
    repo.git.reset(*args)


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

    indexTreeOid: Oid = repo.index.write_tree()
    fallbackSignature = repo.default_signature

    newCommitOid: Oid = repo.create_commit(
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
    tag: git.Tag = next(filter(lambda tag: tag.name == tagName, repo.tags))
    return tag.commit.hexsha


def getOidsForAllReferences(repo: Repository) -> list[Oid]:
    """
    Return commit oids at the tip of all branches, tags, etc. in the repository.

    To ensure a consistent outcome across multiple walks of the same commit graph,
    the oids are sorted by descending commit time.
    """
    tips = []
    for ref in repo.listall_reference_objects():
        ref: pygit2.Reference
        if type(ref.target) != Oid:
            # Skip symbolic reference
            continue
        try:
            commit: Commit = ref.peel(Commit)
            tips.append(commit)
        except pygit2.InvalidSpecError as e:
            # Some refs might not be committish, e.g. in linux's source repo
            print(F"{e} - Skipping ref '{ref.name}'")
            pass
    tips = sorted(tips, key=lambda commit: commit.commit_time, reverse=True)
    return [commit.oid for commit in tips]


def stageFiles(repo: Repository, patches: list[pygit2.Patch]):
    index = repo.index
    for patch in patches:
        if patch.delta.status == pygit2.GIT_DELTA_DELETED:
            index.remove(patch.delta.new_file.path)
        else:
            index.add(patch.delta.new_file.path)
    index.write()


def discardFiles(repo: Repository, paths: list[str]):
    strategy = pygit2.GIT_CHECKOUT_FORCE \
             | pygit2.GIT_CHECKOUT_REMOVE_UNTRACKED \
             | pygit2.GIT_CHECKOUT_DONT_UPDATE_INDEX \
             | pygit2.GIT_CHECKOUT_DISABLE_PATHSPEC_MATCH

    repo.index.read()  # refresh index before getting indexTree
    indexTree = repo[repo.index.write_tree()]
    repo.checkout_tree(indexTree, paths=paths, strategy=strategy)


def unstageFiles(repo: Repository, patches: list[pygit2.Patch]):
    index = repo.index

    if repo.head_is_unborn:
        headTree = None
    else:
        headTree = repo.head.peel(pygit2.Tree)

    for patch in patches:
        delta: pygit2.DiffDelta = patch.delta
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
