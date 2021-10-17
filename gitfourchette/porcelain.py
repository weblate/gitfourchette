from pygit2 import Commit, Diff, Oid, Repository
import pygit2

def loadDirtyDiff(repo: Repository) -> Diff:
    dirtyDiff : Diff = repo.diff(None, None, flags=pygit2.GIT_DIFF_INCLUDE_UNTRACKED)
    dirtyDiff.find_similar()
    return dirtyDiff

def loadStagedDiff(repo: Repository) -> Diff:
    # TODO: need special case for empty repo (can't compare against HEAD)
    stageDiff : Diff = repo.diff('HEAD', None, cached=True)  # compare HEAD to index
    stageDiff.find_similar()
    return stageDiff

def hasAnyStagedChanges(repo: Repository) -> bool:
    status : dict[str, int] = repo.status()
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

def commit(repo: Repository, message: str) -> Oid:
    head = repo.head
    headCommit : Commit = head.peel(Commit)
    indexTreeOid : Oid = repo.index.write_tree()
    parents = [ headCommit.oid ]
    newCommitOid : Oid = repo.create_commit(
        head.name,
        repo.default_signature, #Author
        repo.default_signature, #Committer
        message,
        indexTreeOid,
        parents
    )
    return newCommitOid

def amend(repo: Repository, message: str):
    raise NotImplementedError("repo.git.commit(message=message, amend=True)")

def getHeadCommitMessage(repo: Repository) -> str:
    raise NotImplementedError("repo.head.commit.message")
    return "TODO: getHeadCommitMessage"

def getHeadCommitOid(repo: Repository) -> Oid:
    commit : Commit = repo.head.peel(Commit)
    return commit.oid

def getActiveBranchFullName(repo: Repository) -> str:
    return repo.head.name

def getActiveBranchShorthand(repo: Repository) -> str:
    return repo.head.shorthand

def getCommitOidFromReferenceName(repo: Repository, refName: str) -> Oid:
    raise NotImplementedError("getCommitOidFromReferenceName")
    ref: git.Reference = next(filter(lambda ref: ref.name == refName, repo.refs))
    return ref.commit.hexsha

def getCommitOidFromTagName(repo: Repository, tagName: str) -> Oid:
    raise NotImplementedError("getCommitOidFromTagName")
    tag: git.Tag = next(filter(lambda tag: tag.name == tagName, repo.tags))
    return tag.commit.hexsha

def getOidsForAllReferences(repo: Repository) -> list[Oid]:
    return [ref.target for ref in repo.listall_reference_objects() if type(ref.target) == Oid]
