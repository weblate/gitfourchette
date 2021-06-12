from allgit import *
import datetime
import os
import patch
import zipfile

TRASH_DIR_NAME = "GitFourchetteTrash"
TRASH_TIME_FORMAT = '%Y-%m-%d_at_%H.%M.%S_%f'


def getTrashPath(repo: Repository) -> str:
    return os.path.join(repo.path, TRASH_DIR_NAME)


def newTrashFileName(repo: Repository, suffix: str) -> str:
    trashDir = getTrashPath(repo)
    os.makedirs(trashDir, exist_ok=True)
    now = datetime.datetime.now().strftime(TRASH_TIME_FORMAT)
    path = os.path.join(trashDir, F'discarded_on_{now}{suffix}')
    print(F'[trash] {os.path.relpath(path, repo.path)}')
    return path


def trashRawPatch(repo: Repository, patch: bytes):
    with open(newTrashFileName(repo, '.patch'), 'wb') as f:
        f.write(patch)


def trashGitDiff(repo: Repository, diff):#TODO: git.Diff):
    if diff.change_type == 'D':
        # It doesn't make sense to back up a file deletion
        return
    lines = patch.makePatchFromGitDiff(repo, diff, allowRawFileAccess=True, allowBinaryPatch=True)
    with open(newTrashFileName(repo, '.patch'), mode='wb') as f:
        for line in lines:
            f.write(line)


def trashUntracked(repo: Repository, path: str):
    with zipfile.ZipFile(newTrashFileName(repo, '.zip'), mode='w', compression=zipfile.ZIP_STORED) as z:
        z.write(os.path.join(repo.workdir, path), arcname=path)
        z.comment = F'Head: {repo.head.commit.hexsha}\nBranch: {repo.active_branch.name}'.encode('utf-8')
