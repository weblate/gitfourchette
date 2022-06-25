import os
import pygit2

from gitfourchette import log
from gitfourchette.qt import *


def iterateWatchList(repo):
    frontier = [repo.workdir]

    while frontier:
        parent = frontier.pop(0)
        yield parent

        for item in os.listdir(parent):
            fullPath = os.path.join(parent, item)
            if os.path.isdir(fullPath) and not repo.path_is_ignored(fullPath):
                frontier.append(fullPath)


class FileWatcher(QObject):
    changeDetected = Signal()

    def __init__(self, repo: pygit2.Repository):
        super().__init__(None)
        self.fsw = QFileSystemWatcher()
        self.fsw.addPaths(iterateWatchList(repo))
        self.fsw.directoryChanged.connect(self.onDirectoryChanged)
        self.fsw.fileChanged.connect(self.onFileChanged)
        self.dirty = False

    def onDirectoryChanged(self, path: str):
        log.info("FSW", f"Directory changed: {path}")
        self.dirty = True
        self.changeDetected.emit()

    def onFileChanged(self, path: str):
        log.info("FSW", f"File changed: {path}")
        self.dirty = True
        self.changeDetected.emit()

