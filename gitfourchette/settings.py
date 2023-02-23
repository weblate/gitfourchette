from gitfourchette import log
from gitfourchette.qt import *
import dataclasses
import enum
import json
import os
import time


TEST_MODE = False


REPO_SETTINGS_DIR = "gitfourchette"


SHORT_DATE_PRESETS = [
    ('ISO', '%Y-%m-%d %H:%M'),
    ('Universal 1', '%d %b %Y %H:%M'),
    ('Universal 2', '%a %d %b %Y %H:%M'),
    ('European 1', '%d/%m/%Y %H:%M'),
    ('European 2', '%d.%m.%Y %H:%M'),
    ('American', '%m/%d/%Y %I:%M %p'),
]

LANGUAGES = [
    "en_US",
    "fr_FR"
]


def encodeBinary(b: QByteArray) -> str:
    return b.toBase64().data().decode('utf-8')


def decodeBinary(encoded: str) -> QByteArray:
    return QByteArray.fromBase64(encoded.encode('utf-8'))


class BasePrefs:
    def getParentDir(self):
        return QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppConfigLocation)

    def _getFullPath(self, forWriting: bool):
        prefsDir = self.getParentDir()
        if not prefsDir:
            return None

        if forWriting:
            os.makedirs(prefsDir, exist_ok=True)

        fullPath = os.path.join(prefsDir, getattr(self, 'filename'))

        if not forWriting and not os.path.isfile(fullPath):
            return None

        return fullPath

    def write(self, force=False):
        if not force and TEST_MODE:
            log.info("prefs", "Disabling write prefs")
            return None

        prefsPath = self._getFullPath(forWriting=True)

        if not prefsPath:
            log.warning("prefs", "Couldn't get path for writing")
            return None

        # Get default values if we're saving a dataclass
        defaults = {}
        if dataclasses.is_dataclass(self):
            for f in dataclasses.fields(self):
                if f.default_factory != dataclasses.MISSING:
                    defaults[f.name] = f.default_factory()
                else:
                    defaults[f.name] = f.default

        # Skip private fields starting with an underscore,
        # and skip fields that are set to the default value
        filtered = {}
        for k in self.__dict__:
            if k.startswith("_"):
                continue
            v = self.__dict__[k]
            if (k not in defaults) or (defaults[k] != v):
                filtered[k] = v

        # Dump the object to disk
        with open(prefsPath, 'wt', encoding='utf-8') as jsonFile:
            json.dump(obj=filtered, fp=jsonFile, indent='\t')

        log.info("prefs", f"Wrote {prefsPath}")
        return prefsPath

    def load(self):
        prefsPath = self._getFullPath(forWriting=False)
        if not prefsPath:  # couldn't be found
            return False

        with open(prefsPath, 'rt', encoding='utf-8') as f:
            obj = json.load(f)
            for k in obj:
                if k.startswith('_'):
                    log.warning("prefs", F"{prefsPath}: skipping illegal key: {k}")
                    continue
                if k not in self.__dict__:
                    log.warning("prefs", F"{prefsPath}: skipping unknown key: {k}")
                    continue

                originalType = type(self.__dict__[k])
                if issubclass(originalType, enum.IntEnum):
                    acceptedType = int
                else:
                    acceptedType = originalType

                if type(obj[k]) != acceptedType:
                    log.warning("prefs", F"{prefsPath}: value type mismatch for {k}: expected {acceptedType}, got {type(obj[k])}")
                    continue
                self.__dict__[k] = originalType(obj[k])

        return True


class PathDisplayStyle(enum.IntEnum):
    FULL_PATHS = 1
    ABBREVIATE_DIRECTORIES = 2
    SHOW_FILENAME_ONLY = 3


class AuthorDisplayStyle(enum.IntEnum):
    FULL_NAME = 1
    FIRST_NAME = 2
    LAST_NAME = 3
    INITIALS = 4
    FULL_EMAIL = 5
    ABBREVIATED_EMAIL = 6


class Verbosity(enum.IntEnum):
    QUIET = 0
    VERBOSE = 1
    VERY_VERBOSE = 2


@dataclasses.dataclass
class Prefs(BasePrefs):
    filename = "prefs.json"

    language                    : str           = ""
    qtStyle                     : str           = ""
    fileWatcher                 : bool          = False
    shortHashChars              : int           = 7
    shortTimeFormat             : str           = SHORT_DATE_PRESETS[0][1]
    pathDisplayStyle            : PathDisplayStyle = PathDisplayStyle.FULL_PATHS
    authorDisplayStyle          : AuthorDisplayStyle = AuthorDisplayStyle.ABBREVIATED_EMAIL
    maxRecentRepos              : int           = 20
    showStatusBar               : bool          = False
    autoHideMenuBar             : bool          = False
    diff_font                   : str           = ""
    diff_tabSpaces              : int           = 4
    diff_largeFileThresholdKB   : int           = 512
    diff_imageFileThresholdKB   : int           = 5000
    diff_wordWrap               : bool          = False
    diff_showStrayCRs           : bool          = True
    diff_colorblindFriendlyColors : bool        = False
    tabs_closeButton            : bool          = True
    tabs_expanding              : bool          = True
    tabs_autoHide               : bool          = False
    tabs_doubleClickOpensFolder : bool          = True
    graph_chronologicalOrder    : bool          = True
    graph_flattenLanes          : bool          = True
    trash_maxFiles              : int           = 250
    trash_maxFileSizeKB         : int           = 1024
    debug_showMemoryIndicator   : bool          = True
    debug_showPID               : bool          = True
    debug_verbosity             : Verbosity     = Verbosity.VERBOSE


@dataclasses.dataclass
class History(BasePrefs):
    filename = "history.json"

    repos: dict = dataclasses.field(default_factory=dict)
    cloneHistory: list[str] = dataclasses.field(default_factory=list)
    fileDialogPaths: dict = dataclasses.field(default_factory=dict)

    def addRepo(self, path: str):
        path = os.path.normpath(path)
        repo = self.getRepo(path)
        repo['time'] = time.time()
        return repo

    def getRepo(self, path) -> dict:
        try:
            repo = self.repos[path]
        except KeyError:
            repo = {}
            self.repos[path] = repo
        return repo

    def getRepoNickname(self, path):
        path = os.path.normpath(path)
        repo = self.getRepo(path)
        return repo.get("nickname", os.path.basename(path))

    def setRepoNickname(self, path: str, nickname: str):
        path = os.path.normpath(path)
        repo = self.getRepo(path)
        nickname = nickname.strip()
        if nickname:
            repo['nickname'] = nickname
        else:
            repo.pop('nickname', None)

    def getRepoNumCommits(self, path: str):
        path = os.path.normpath(path)
        repo = self.getRepo(path)
        return repo.get('length', 0)

    def setRepoNumCommits(self, path: str, commitCount: int):
        path = os.path.normpath(path)
        repo = self.getRepo(path)
        if commitCount > 0:
            repo['length'] = commitCount
        else:
            repo.pop('length', None)

    def removeRepo(self, path: str):
        path = os.path.normpath(path)
        self.repos.pop(path, None)

    def clearRepoHistory(self):
        self.repos.clear()

    def getRecentRepoPaths(self, n: int, newestFirst=True):
        sortedPaths = (path for path, _ in
                       sorted(self.repos.items(), key=lambda i: i[1].get('time', 0), reverse=newestFirst))

        return (path for path, _ in zip(sortedPaths, range(n)))

    def write(self, force=False):
        self.trim()
        super().write(force)

    def trim(self):
        n = prefs.maxRecentRepos

        if len(self.repos) > n:
            # Recreate self.repos with only the n most recent paths
            topPaths = self.getRecentRepoPaths(n)
            self.repos = {path: self.repos[path] for path in topPaths}

        if len(self.cloneHistory) > n:
            self.cloneHistory = self.cloneHistory[-n:]

    def addCloneUrl(self, url):
        try:
            self.cloneHistory.remove(url)
        except ValueError:
            pass
        self.cloneHistory.append(url)

    def clearCloneHistory(self):
        self.cloneHistory.clear()


@dataclasses.dataclass
class Session(BasePrefs):
    filename = "session.json"

    tabs                        : list[str]     = dataclasses.field(default_factory=list)
    activeTabIndex              : int           = -1
    windowGeometry              : str           = ""
    splitterStates              : dict          = dataclasses.field(default_factory=dict)


# Initialize default prefs and history.
# The app should load the user's prefs with prefs.load() and history.load().
prefs = Prefs()
history = History()



def applyQtStylePref(forceApplyDefault: bool):
    app = QApplication.instance() 

    if prefs.qtStyle:
        app.setStyle(prefs.qtStyle)
    elif forceApplyDefault:
        app.setStyle(app.PLATFORM_DEFAULT_STYLE_NAME)

    if MACOS:
        isDefaultMacStyle = (not prefs.qtStyle) or (prefs.qtStyle.lower() == "macos")
        app.setAttribute(Qt.ApplicationAttribute.AA_DontShowIconsInMenus, isDefaultMacStyle)
