from gitfourchette import log
from gitfourchette import settings
import datetime
import os
import pygit2
import shutil


class Trash:
    DIR_NAME = "trash"
    TIME_FORMAT = '%Y%m%dT%H%M%S'

    def __init__(self, repo: pygit2.Repository):
        self.repo = repo
        self.trashDir = os.path.join(repo.path, settings.REPO_SETTINGS_DIR, Trash.DIR_NAME)
        self.trashFiles = []
        self.refreshFiles()

    def exists(self):
        return os.path.isdir(self.trashDir)

    def refreshFiles(self):
        self.trashFiles = []
        if os.path.isdir(self.trashDir):
            files = os.listdir(self.trashDir)
            self.trashFiles = sorted(files, reverse=True)

    def makeRoom(self, maxFiles=-1):
        if maxFiles < 0:
            maxFiles = max(0, settings.prefs.trash_maxFiles-1)

        while len(self.trashFiles) > maxFiles:
            f = self.trashFiles.pop()
            fullPath = os.path.join(self.trashDir, f)
            if os.path.isfile(fullPath):
                log.info("trash", "Deleting trash file", fullPath)
                os.unlink(fullPath)

    def newFile(self, ext: str = "", originalPath: str = "") -> str:
        os.makedirs(self.trashDir, exist_ok=True)

        now = datetime.datetime.now().strftime(Trash.TIME_FORMAT)
        baseName = os.path.basename(originalPath)

        path = os.path.join(self.trashDir, F'{now}-{baseName}{ext}')

        # If a file exists at this path, tack a number to the end of the name.
        for differentiator in range(2, 100):  # If we reach 99, just overwrite the last one.
            if os.path.exists(path):
                path = os.path.join(self.trashDir, F'{now}-{baseName}({differentiator}){ext}')
            else:
                break

        self.makeRoom()
        self.trashFiles.insert(0, path)

        return path

    def backupFile(self, path: str):
        fullPath = os.path.join(self.repo.workdir, path)

        if os.lstat(fullPath).st_size > 1024*settings.prefs.trash_maxFileSizeKB:
            return None

        # Copy new file
        trashedPath = self.newFile(originalPath=path)
        shutil.copyfile(fullPath, trashedPath)
        return trashedPath

    def backupPatch(self, data: bytes, originalPath: str = ""):
        trashFile = self.newFile(ext=".patch", originalPath=originalPath)
        with open(trashFile, 'wb') as f:
            f.write(data)

    def backupPatches(self, patches: list[pygit2.Patch]):
        for patch in patches:
            path = patch.delta.new_file.path

            if patch.delta.status == pygit2.GIT_DELTA_DELETED:
                # It doesn't make sense to back up a file deletion
                continue

            elif patch.delta.status == pygit2.GIT_DELTA_UNTRACKED or patch.delta.is_binary:
                self.backupFile(path)

            else:
                # Write text patch
                self.backupPatch(patch.data, path)

    def getSize(self):
        size = 0
        count = 0

        for f in self.trashFiles:
            filePath = os.path.join(self.trashDir, f)
            if os.path.isfile(filePath):
                size += os.lstat(filePath).st_size
                count += 1

        return size, count

    def clear(self):
        self.makeRoom(0)
