import datetime
import git
import os
import patch
import zipfile

TRASH_DIR_NAME = "GitFourchetteTrash"
TRASH_TIME_FORMAT = '%Y-%m-%d_at_%H.%M.%S_%f'


def getTrashPath(repo: git.Repo) -> str:
    return os.path.join(repo.git_dir, TRASH_DIR_NAME)


def newTrashFileName(repo: git.Repo, suffix: str) -> str:
    trashDir = getTrashPath(repo)
    os.makedirs(trashDir, exist_ok=True)
    now = datetime.datetime.now().strftime(TRASH_TIME_FORMAT)
    path = os.path.join(trashDir, F'discarded_on_{now}{suffix}')
    print(F'[trash] {os.path.relpath(path, repo.git_dir)}')
    return path


def trashRawPatch(repo: git.Repo, patch: bytes):
    with open(newTrashFileName(repo, '.patch'), 'wb') as f:
        f.write(patch)


def trashGitDiff(repo: git.Repo, diff: git.Diff):
    if diff.change_type == 'D':
        # It doesn't make sense to back up a file deletion
        return
    lines = patch.makePatchFromGitDiff(repo, diff, allowRawFileAccess=True, allowBinaryPatch=True)
    with open(newTrashFileName(repo, '.patch'), mode='wb') as f:
        for line in lines:
            f.write(line)


def trashUntracked(repo: git.Repo, path: str):
    with zipfile.ZipFile(newTrashFileName(repo, '.zip'), mode='w', compression=zipfile.ZIP_STORED) as z:
        z.write(os.path.join(repo.working_tree_dir, path), arcname=path)
        z.comment = F'Head: {repo.head.commit.hexsha}\nBranch: {repo.active_branch.name}'.encode('utf-8')
