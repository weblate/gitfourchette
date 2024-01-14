import datetime
import logging
import os
import shutil

from gitfourchette import settings
from gitfourchette.porcelain import *
from gitfourchette.qt import *

logger = logging.getLogger(__name__)


class Trash:
    DIR_NAME = "trash"
    TIME_FORMAT = '%Y%m%d-%H%M%S'
    _instance = None

    def __init__(self):
        if settings.TEST_MODE:
            template = os.path.join(QDir.tempPath(), QApplication.applicationName() + "-trash")
            tempDir = QTemporaryDir(template)
            self.trashDir = tempDir.path()
        else:
            cacheDir = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation)
            self.trashDir = os.path.join(cacheDir, Trash.DIR_NAME)
        self.trashFiles = []
        self.refreshFiles()

    @staticmethod
    def instance():
        if not Trash._instance:
            Trash._instance = Trash()
        return Trash._instance

    @property
    def maxFileCount(self) -> int:
        return settings.prefs.trash_maxFiles

    @property
    def maxFileSize(self) -> int:
        return settings.prefs.trash_maxFileSizeKB * 1024

    def exists(self):
        return os.path.isdir(self.trashDir)

    def refreshFiles(self):
        self.trashFiles = []
        if os.path.isdir(self.trashDir):
            files = os.listdir(self.trashDir)
            self.trashFiles = sorted(files, reverse=True)

    def makeRoom(self, maxFiles: int):
        while len(self.trashFiles) > maxFiles:
            f = self.trashFiles.pop()
            fullPath = os.path.join(self.trashDir, f)
            if os.path.isfile(fullPath):
                logger.debug(f"Deleting trash file {fullPath}")
                os.unlink(fullPath)

    def newFile(self, workdir: str, ext: str = "", originalPath: str = "") -> str:
        maxFiles = self.maxFileCount
        if maxFiles == 0:
            return ""

        maxFiles = max(0, maxFiles - 1)
        self.makeRoom(maxFiles)

        os.makedirs(self.trashDir, exist_ok=True)

        now = datetime.datetime.now().strftime(Trash.TIME_FORMAT)
        wdID = os.path.basename(os.path.normpath(workdir))
        base = os.path.basename(os.path.normpath(originalPath))
        stem = f"{now}-{wdID}---{base}"
        path = os.path.join(self.trashDir, stem + ext)

        # If a file exists at this path, tack a number to the end of the name.
        for differentiator in range(2, 100):  # If we reach 99, just overwrite the last one.
            if os.path.exists(path):
                path = os.path.join(self.trashDir, f"{stem}({differentiator}){ext}")
            else:
                break

        self.trashFiles.insert(0, path)
        return path

    def backupFile(self, workdir: str, originalPath: str) -> str:
        fullPath = os.path.join(workdir, originalPath)

        if os.lstat(fullPath).st_size > self.maxFileSize:
            return ""

        # Copy new file
        trashPath = self.newFile(workdir, originalPath=originalPath)
        if not trashPath:
            return ""

        shutil.copyfile(fullPath, trashPath)
        return trashPath

    def backupPatch(self, workdir: str, data: bytes, originalPath: str = ""):
        trashFile = self.newFile(workdir, ext=".patch", originalPath=originalPath)
        if not trashFile:
            return ""
        with open(trashFile, 'wb') as f:
            f.write(data)
        return trashFile

    def backupPatches(self, workdir: str, patches: list[Patch]):
        for patch in patches:
            path = patch.delta.new_file.path

            if patch.delta.status == GIT_DELTA_DELETED:
                # It doesn't make sense to back up a file deletion
                continue

            elif patch.delta.status == GIT_DELTA_UNTRACKED or patch.delta.is_binary:
                self.backupFile(workdir, path)

            else:
                # Write text patch
                self.backupPatch(workdir, patch.data, path)

    def size(self) -> tuple[int, int]:
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
