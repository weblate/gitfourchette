from dataclasses import dataclass, field
from gitfourchette import log
from gitfourchette.qt import *
import enum
import json
import os


TEST_MODE = False


REPO_SETTINGS_DIR = "gitfourchette"


KEYS_ACCEPT = [Qt.Key_Enter, Qt.Key_Return]  # Enter = on keypad; Return = main keys
KEYS_REJECT = [Qt.Key_Delete, Qt.Key_Backspace]


SHORT_DATE_PRESETS = [
    ('ISO', '%Y-%m-%d %H:%M'),
    ('Universal', '%d %b %Y %H:%M'),
    ('European', '%d/%m/%Y %H:%M'),
    ('American', '%m/%d/%Y %I:%M %p'),
]


def encodeBinary(b: QByteArray) -> str:
    return b.toBase64().data().decode('utf-8')


def decodeBinary(encoded: str) -> QByteArray:
    return QByteArray.fromBase64(encoded.encode('utf-8'))


class BasePrefs:
    def getParentDir(self):
        return QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation)

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

    def write(self):
        if TEST_MODE:
            log.info("prefs", "Disabling write prefs")
            return None

        prefsPath = self._getFullPath(forWriting=True)

        if not prefsPath:
            log.warning("prefs", "Couldn't get path for writing")
            return None

        with open(prefsPath, 'w', encoding='utf-8') as jsonFile:
            json.dump(
                obj={k: self.__dict__[k] for k in self.__dict__ if not k.startswith("_")},
                fp=jsonFile,
                indent='\t')

        return prefsPath

    def load(self):
        prefsPath = self._getFullPath(forWriting=False)
        if not prefsPath:  # couldn't be found
            return False

        with open(prefsPath, 'r') as f:
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


@dataclass
class Prefs(BasePrefs):
    filename = "prefs.json"

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
    graph_chronologicalOrder    : bool          = True
    graph_maxLanes              : int           = 32
    graph_flattenLanes          : bool          = True
    graph_newLanesAlwaysRightmost:bool          = False
    trash_maxFiles              : int           = 250
    trash_maxFileSizeKB         : int           = 1024
    debug_showMemoryIndicator   : bool          = True
    debug_showDirtyCommitsAfterRefresh : bool   = True
    debug_showPID               : bool          = True


@dataclass
class History(BasePrefs):
    filename = "history.json"

    fileDialogPaths             : dict          = field(default_factory=dict)
    history                     : list[str]     = field(default_factory=list)
    nicknames                   : dict          = field(default_factory=dict)
    cloneHistory                : list[str]     = field(default_factory=list)

    def _addToList(self, item, list):
        try:
            list.remove(item)
        except ValueError:
            pass
        list.append(item)
        self.trim()
        self.write()

    def addRepo(self, path):
        path = os.path.normpath(path)
        self._addToList(path, self.history)

    def getRepoNickname(self, path):
        path = os.path.normpath(path)
        if path in self.nicknames:
            return self.nicknames[path]
        else:
            return os.path.basename(path)

    def setRepoNickname(self, path: str, nickname: str):
        path = os.path.normpath(path)
        nickname = nickname.strip()
        if not nickname:
            if path not in self.nicknames:
                # no nickname given, no existing nickname in history: no-op
                return
            del self.nicknames[path]
        else:
            self.nicknames[path] = nickname
        self.write()

    def removeRepo(self, path):
        path = os.path.normpath(path)
        self.history.remove(path)
        if path in self.nicknames:
            del self.nicknames[path]
        self.write()

    def clearRepoHistory(self):
        self.history.clear()
        self.nicknames.clear()
        self.write()

    def clearCloneHistory(self):
        self.cloneHistory.clear()
        self.write()

    def trim(self):
        n = prefs.maxRecentRepos

        if len(self.history) > n:
            for path in self.history[:-n]:
                self.nicknames.pop(path, None)
            self.history = self.history[-n:]

        if len(self.cloneHistory) > n:
            self.cloneHistory = self.cloneHistory[-n:]

    def addCloneUrl(self, url):
        self._addToList(url, self.cloneHistory)


@dataclass
class Session(BasePrefs):
    filename = "session.json"

    tabs                        : list[str]     = field(default_factory=list)
    activeTabIndex              : int           = -1
    windowGeometry              : str           = ""
    splitterStates              : dict          = field(default_factory=dict)


# Initialize default prefs and history.
# The app should load the user's prefs with prefs.load() and history.load().
prefs = Prefs()
history = History()

