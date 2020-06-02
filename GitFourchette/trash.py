import os
import git
import datetime
import zipfile
import patch


TRASH_DIR_NAME = "GitFourchetteTrash"
TRASH_TIME_FORMAT = '%Y%m%d_%H%M%S_%f'


def newTrashFileName(repo: git.Repo, suffix: str) -> str:
    trashDir = os.path.join(repo.git_dir, TRASH_DIR_NAME)
    os.makedirs(trashDir, exist_ok=True)
    now = datetime.datetime.now().strftime(TRASH_TIME_FORMAT)
    path = os.path.join(trashDir, F'{now}{suffix}')
    print(F'Trash: {os.path.relpath(path, repo.git_dir)}')
    return path


def trashGitDiff(repo: git.Repo, diff: git.Diff):
    lines = patch.makePatchFromGitDiff(repo, diff)
    with open(newTrashFileName(repo, '.patch'), 'w') as f:
        f.writelines(lines)


def trashUntracked(repo: git.Repo, path: str):
    with zipfile.ZipFile(newTrashFileName(repo, '.zip'), mode='w', compression=zipfile.ZIP_STORED) as z:
        z.write(os.path.join(repo.working_tree_dir, path), arcname=path)
        z.comment = F'Head: {repo.head.commit.hexsha}\nBranch: {repo.active_branch.name}'.encode('utf-8')
