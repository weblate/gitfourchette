from pygit2 import Commit, Diff, Oid, Repository
import pygit2


def loadDirtyDiff(repo: Repository) -> Diff:
    dirtyDiff : Diff = repo.diff(None, None, flags=pygit2.GIT_DIFF_INCLUDE_UNTRACKED)
    dirtyDiff.find_similar()
    return dirtyDiff


def loadStagedDiff(repo: Repository) -> Diff:
    # TODO: need special case for empty repo (can't compare against HEAD)
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
    commit: Commit = repo.get(oid)
    #import time; time.sleep(1) #to debug out-of-order events
    return [repo.diff(parent, commit) for parent in commit.parents]


def switchToBranch(repo: Repository, newBranch: str):
    raise NotImplementedError("repo.git.switch('--no-guess', newBranch)")


def renameBranch(repo: Repository, oldName: str, newName: str):
    # TODO: if the branch tracks an upstream branch, issue a warning that it won't be renamed on the server
    raise NotImplementedError("repo.git.branch(oldName, newName, m=True)")


def deleteBranch(repo: Repository, localBranchName: str):
    raise NotImplementedError("repo.git.branch(localBranchName, d=True)")


def newBranch(repo: Repository, localBranchName: str):
    raise NotImplementedError("repo.git.branch(localBranchName)")


def newTrackingBranch(repo: Repository, localBranchName: str, remoteBranchName: str):
    raise NotImplementedError("repo.git.branch('--track', localBranchName, remoteBranchName)")


def newBranchFromCommit(repo: Repository, localBranchName: str, commitOid: Oid):
    raise NotImplementedError("repo.git.branch(localBranchName, commitHexsha)")
    switchToBranch(repo, localBranchName)


def editTrackingBranch(repo: Repository, localBranchName: str, remoteBranchName: str):
    raise NotImplementedError("edit tracking branch")
    localBranch: git.Head = repo.heads[localBranchName]
    remoteBranch: git.Reference = None
    if remoteBranchName:
        remoteBranch = repo.refs[remoteBranchName]
    localBranch.set_tracking_branch(remoteBranch)


def editRemoteURL(repo: Repository, remoteName: str, newURL: str):
    raise NotImplementedError("edit remote URL")
    remote = repo.remote(remoteName)
    remote.set_url(newURL)


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


def createCommit(repo: Repository, message: str) -> Oid:
    head = repo.head
    indexTreeOid: Oid = repo.index.write_tree()
    parents = [getHeadCommitOid(repo)]
    newCommitOid: Oid = repo.create_commit(
        head.name,
        repo.default_signature, #Author
        repo.default_signature, #Committer
        message,
        indexTreeOid,
        parents
    )
    return newCommitOid


def amendCommit(repo: Repository, message: str) -> Oid:
    indexTreeOid = repo.index.write_tree(repo)
    newCommitOid = repo.amend_commit(
        getHeadCommit(repo),
        'HEAD',
        message=message,
        committer=repo.default_signature,
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
    headTree = repo.head.peel(pygit2.Tree)
    for patch in patches:
        delta: pygit2.DiffDelta = patch.delta
        old_path = delta.old_file.path
        new_path = delta.new_file.path
        if delta.status == pygit2.GIT_DELTA_ADDED:
            assert old_path not in headTree
            index.remove(old_path)
        elif delta.status == pygit2.GIT_DELTA_RENAMED:
            # TODO: Two-step removal to completely unstage a rename -- is this what we want?
            assert new_path in index
            index.remove(new_path)
        else:
            assert old_path in headTree
            obj = headTree[old_path]
            index.add(pygit2.IndexEntry(old_path, obj.oid, obj.filemode))
    index.write()
