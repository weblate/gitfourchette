import contextlib
import os
import pygit2

from gitfourchette import log
from gitfourchette import settings
from gitfourchette import util
from gitfourchette.benchmark import Benchmark
from gitfourchette.qt import *


TAG = "FSW"


def walkWatchableDirs(repo: pygit2.Repository, startDir=""):
    if not startDir:
        startDir = os.path.normpath(repo.workdir)

    frontier = [startDir]

    while frontier:
        parent = frontier.pop(0)
        yield parent

        for item in os.scandir(parent):
            if item.is_dir():
                p = item.path
                if not repo.path_is_ignored(p):
                    frontier.append(p)


class FileWatcher(QObject):
    directoryChanged = Signal()
    indexChanged = Signal()

    repo: pygit2.Repository
    fsw: QFileSystemWatcher
    rewatchDelay: QTimer
    pendingRewatch: set[str]

    @property
    def indexFilePath(self):
        return os.path.join(self.repo.path, "index")

    def __init__(self, parent: QObject, repo: pygit2.Repository, delayMilliseconds=100):
        super().__init__(parent)

        self.repo = repo
        self.fsw = None
        self.rewatchDelay = None
        self.pendingRewatch = []

        if settings.prefs.fileWatcher:
            self.boot(delayMilliseconds)

    def boot(self, delayMilliseconds=100):
        if self.fsw:
            return

        self.fsw = QFileSystemWatcher(self)

        with Benchmark("Collect paths to watch"):
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
        self.fsw.addPath(self.indexFilePath)

    def shutdown(self):
        if not self.fsw:
            return

        self.fsw.directoryChanged.disconnect(self.onDirectoryChanged)
        self.fsw.fileChanged.disconnect(self.onFileChanged)
        self.fsw.deleteLater()
        self.fsw = None

        self.rewatchDelay.stop()
        self.rewatchDelay.deleteLater()
        self.rewatchDelay = None

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
        if self.rewatchDelay.interval() > 0:
            self.rewatchDelay.start()
        else:
            self.rewatchDelay.timeout.emit()

    def onFileChanged(self, path: str):
        if path == self.indexFilePath:
            # The index file may be deleted and rewritten.
            # In that case the FSW stops watching the file, so re-add it to keep watching.
            if path not in self.fsw.files():
                self.fsw.addPath(path)
            log.info(TAG, f"Index changed")
            self.indexChanged.emit()

    def stopWatchingIndex(self):
        self.fsw.removePath(self.indexFilePath)

    def startWatchingIndex(self):
        self.fsw.addPath(self.indexFilePath)

    def blockWatchingIndex(self):
        """
        Returns a context manager that temporarily ignores updates to the
        repository's index file.

        When you perform an operation that modifies the index via pygit2,
        prefer using this context manager over a QSignalBlocker.

        With QSignalBlocker (not recommended!) the signal may still fire after
        you're done modifying the index, because the QFileSystemWatcher is
        unlikely to detect a change to the index file immediately.
        """

        if not self.fsw:
            return contextlib.nullcontext()

        fw = self

        class IndexWatchBlocker:
            def __enter__(self):
                assert not util.onAppThread()
                fw.stopWatchingIndex()

            def __exit__(self, exc_type, exc_val, exc_tb):
                assert not util.onAppThread()
                fw.startWatchingIndex()

        return IndexWatchBlocker()
