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
    changeDetected = Signal()

    repo: pygit2.Repository
    fsw: QFileSystemWatcher
    rewatchDelay: QTimer
    pendingRewatch: set[str]

    def __init__(self, repo: pygit2.Repository, delayMilliseconds=100):
        super().__init__(None)

        self.repo = repo

        self.fsw = QFileSystemWatcher()
        self.fsw.addPaths(walkWatchableDirs(self.repo))

        self.fsw.directoryChanged.connect(self.onDirectoryChanged)
        self.fsw.fileChanged.connect(self.onFileChanged)

        self.pendingRewatch = set()

        self.rewatchDelay = QTimer(self)
        self.rewatchDelay.setSingleShot(True)
        self.rewatchDelay.setInterval(delayMilliseconds)
        self.rewatchDelay.timeout.connect(self.onRewatchTimeout)

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
                self.fsw.addPaths(walkWatchableDirs(self.repo, fullChildPath))

        zombieChildren = [d for d in recursiveChildren if not os.path.isdir(d)]
        if zombieChildren:
            log.info(TAG, f"Removing zombie children: {self.prettifyPathList(zombieChildren)}")
            self.fsw.removePaths(zombieChildren)

    def onRewatchTimeout(self):
        log.info(TAG, f"Directories changed: {self.prettifyPathList(self.pendingRewatch)}")
        for d in self.pendingRewatch:
            self.refreshDirectory(d)
        self.pendingRewatch.clear()
        log.info(TAG, f"Watched: {self.prettifyPathList(self.fsw.directories())}")
        self.changeDetected.emit()

    def onDirectoryChanged(self, path: str):
        self.pendingRewatch.add(path)
        self.rewatchDelay.start()

    def onFileChanged(self, path: str):
        log.info(TAG, f"File changed: {path}")
        self.changeDetected.emit()

