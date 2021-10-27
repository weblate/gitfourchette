from allgit import *
import datetime
import os
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


def backupPatches(repo: Repository, patches: list[Patch]):
    with zipfile.ZipFile(newTrashFileName(repo, '.zip'), mode='w', compression=zipfile.ZIP_STORED) as z:
        z.comment = F'Head: {repo.head.target}\nBranch: {repo.head.shorthand}'.encode('utf-8')
        for patch in patches:
            path = patch.delta.new_file.path
            if patch.delta.status == pygit2.GIT_DELTA_DELETED:
                # It doesn't make sense to back up a file deletion
                pass
            elif patch.delta.status == pygit2.GIT_DELTA_UNTRACKED or patch.delta.is_binary:
                # Copy new file to zip
                z.write(os.path.join(repo.workdir, path), arcname=path)
            else:
                # Copy text patch
                z.writestr(path + ".patch", patch.data)
