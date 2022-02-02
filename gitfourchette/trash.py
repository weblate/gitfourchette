from allgit import *
from settings import REPO_SETTINGS_DIR
import datetime
import os
import shutil

TRASH_DIR_NAME = "trash"
TRASH_TIME_FORMAT = '%Y%m%dT%H%M%S'


def getTrashPath(repo: Repository) -> str:
    return os.path.join(repo.path, REPO_SETTINGS_DIR, TRASH_DIR_NAME)


def newTrashFileName(repo: Repository, ext: str = "", originalPath: str = "") -> str:
    trashDir = getTrashPath(repo)
    os.makedirs(trashDir, exist_ok=True)

    now = datetime.datetime.now().strftime(TRASH_TIME_FORMAT)
    baseName = os.path.basename(originalPath)

    path = os.path.join(trashDir, F'{now}-{baseName}{ext}')

    # If a file exists at this path, tack a number to the end of the name.
    for differentiator in range(2, 100):  # If we reach 99, just overwrite the last one.
        if os.path.exists(path):
            path = os.path.join(trashDir, F'{now}-{baseName}({differentiator}){ext}')
        else:
            break

    return path


def backupPatch(repo: Repository, data: bytes, originalPath: str = ""):
    with open(newTrashFileName(repo, ext=".patch", originalPath=originalPath), 'wb') as f:
        f.write(data)


def backupPatches(repo: Repository, patches: list[Patch]):
    for patch in patches:
        path = patch.delta.new_file.path

        if patch.delta.status == pygit2.GIT_DELTA_DELETED:
            # It doesn't make sense to back up a file deletion
            continue

        elif patch.delta.status == pygit2.GIT_DELTA_UNTRACKED or patch.delta.is_binary:
            # Copy new file
            trashedPath = newTrashFileName(repo, originalPath=path)
            shutil.copyfile(os.path.join(repo.workdir, path), trashedPath)

        else:
            # Write text patch
            backupPatch(repo, patch.data, path)


def getTrashSize(repo: Repository):
    path = getTrashPath(repo)

    size = 0

    if os.path.isdir(path):
        for f in os.listdir(path):
            filePath = os.path.join(path, f)
            if os.path.isfile(filePath):
                size += os.lstat(filePath).st_size

    return size


def clearTrash(repo: Repository):
    path = getTrashPath(repo)

    if os.path.isdir(path):
        files = list(os.listdir(path))

        for f in files:
            filePath = os.path.join(path, f)
            if os.path.isfile(filePath):
                os.unlink(filePath)

