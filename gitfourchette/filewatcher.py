import os
import pygit2

from gitfourchette import log
from gitfourchette.qt import *


TAG = "FSW"


def walkWatchableDirs(repo: pygit2.Repository, startDir=""):
    if not startDir:
        startDir = os.path.normpath(repo.workdir)

    frontier = [startDir]

    while frontier:
        parent = frontier.pop(0)
        yield parent

        for item in os.listdir(parent):
            fullPath = os.path.join(parent, item)
            if os.path.isdir(fullPath) and not repo.path_is_ignored(fullPath):
                frontier.append(fullPath)


class FileWatcher(QObject):
    directoryChanged = Signal()
    indexChanged = Signal()

    repo: pygit2.Repository
    fsw: QFileSystemWatcher
    rewatchDelay: QTimer
    pendingRewatch: set[str]

    def __init__(self, repo: pygit2.Repository, delayMilliseconds=100):
        super().__init__(None)

        self.repo = repo

        self.fsw = QFileSystemWatcher()
        failed = self.fsw.addPaths(walkWatchableDirs(self.repo))
        if failed:
            log.warning(TAG, f"{len(failed)} paths failed to be watched")

        self.fsw.directoryChanged.connect(self.onDirectoryChanged)
        self.fsw.fileChanged.connect(self.onFileChanged)

        self.pendingRewatch = set()

        self.rewatchDelay = QTimer(self)
        self.rewatchDelay.setSingleShot(True)
        self.rewatchDelay.setInterval(delayMilliseconds)
        self.rewatchDelay.timeout.connect(self.onRewatchTimeout)

        # Watch index file as well
        self.fsw.addPath(os.path.join(repo.path, "index"))

    def prettifyPathList(self, pathList):
        prefix = os.path.normpath(self.repo.workdir) + "/"
        return [d.removeprefix(prefix) for d in pathList]

    def refreshDirectory(self, path: str):
        assert path == os.path.normpath(path)

        recursiveChildren = {d for d in self.fsw.directories()
                             if d.startswith(path)}

        directChildren = {d for d in recursiveChildren
                          if os.path.split(d)[0] == path}

        for childItem in os.listdir(path):
            fullChildPath = os.path.join(path, childItem)
            if (os.path.isdir(fullChildPath)
                    and fullChildPath not in directChildren
                    and not self.repo.path_is_ignored(fullChildPath)):
                log.info(TAG, f"Watching new directory: {fullChildPath}")
                failed = self.fsw.addPaths(walkWatchableDirs(self.repo, fullChildPath))
                if failed:
                    log.warning(TAG, f"{len(failed)} paths failed to be watched")

        zombieChildren = [d for d in recursiveChildren if not os.path.isdir(d)]
        if zombieChildren:
            log.info(TAG, f"Removing zombie children: {self.prettifyPathList(zombieChildren)}")
            self.fsw.removePaths(zombieChildren)

    def onRewatchTimeout(self):
        log.info(TAG, f"Directories changed: {self.prettifyPathList(self.pendingRewatch)}")
        for d in self.pendingRewatch:
            self.refreshDirectory(d)
        self.pendingRewatch.clear()
        log.info(TAG, f"Directory watchlist: {self.prettifyPathList(self.fsw.directories())}")
        self.directoryChanged.emit()

    def onDirectoryChanged(self, path: str):
        self.pendingRewatch.add(path)
        self.rewatchDelay.start()

    def onFileChanged(self, path: str):
        if path == os.path.join(self.repo.path, "index"):
            # The index file may be deleted and rewritten.
            # In that case the FSW stops watching the file, so re-add it to keep watching.
            if path not in self.fsw.files():
                self.fsw.addPath(path)
            log.info(TAG, f"Index changed")
            self.indexChanged.emit()
