from allqt import *
from dataclasses import dataclass, field
import enum
import json
import os


TEST_MODE = False


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
    def write(self):
        if TEST_MODE:
            print("Disabling write prefs")
            return None
        prefsDir = QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation)
        os.makedirs(prefsDir, exist_ok=True)
        prefsPath = os.path.join(prefsDir, getattr(self, 'filename'))
        with open(prefsPath, 'w', encoding='utf-8') as f:
            json.dump(self.__dict__, f, indent='\t')
        return prefsPath

    def load(self):
        prefsPath = QStandardPaths.locate(QStandardPaths.AppConfigLocation, getattr(self, 'filename'))
        if not prefsPath:  # couldn't be found
            return False

        with open(prefsPath, 'r') as f:
            obj = json.load(f)
            for k in obj:
                if k.startswith('_'):
                    print(F"{prefsPath}: skipping illegal key: {k}")
                    continue
                if k not in self.__dict__:
                    print(F"{prefsPath}: skipping unknown key: {k}")
                    continue

                originalType = type(self.__dict__[k])
                if issubclass(originalType, enum.IntEnum):
                    acceptedType = int
                else:
                    acceptedType = originalType

                if type(obj[k]) != acceptedType:
                    print(F"{prefsPath}: value type mismatch for {k}: expected {acceptedType}, got {type(obj[k])}")
                    continue
                self.__dict__[k] = originalType(obj[k])

        return True


class PathDisplayStyle(enum.IntEnum):
    FULL_PATHS = 1,
    ABBREVIATE_DIRECTORIES = 2,
    SHOW_FILENAME_ONLY = 3,


@dataclass
class Prefs(BasePrefs):
    filename = "prefs.json"

    qtStyle                     : str           = ""
    shortHashChars              : int           = 7
    shortTimeFormat             : str           = SHORT_DATE_PRESETS[0][1]
    pathDisplayStyle            : PathDisplayStyle = PathDisplayStyle.ABBREVIATE_DIRECTORIES
    showStatusBar               : bool          = True
    diff_font                   : str           = ""
    diff_tabSpaces              : int           = 4
    diff_largeFileThreshold     : int           = 300000
    diff_wordWrap               : bool          = False
    diff_showStrayCRs           : bool          = True
    diff_colorblindFriendlyColors : bool        = False
    tabs_closeButton            : bool          = True
    tabs_expanding              : bool          = True
    tabs_autoHide               : bool          = False
    tabs_mergeWithMenubar       : bool          = False
    graph_topoOrder             : bool          = True
    graph_maxLanes              : int           = 32
    graph_flattenLanes          : bool          = True
    graph_newLanesAlwaysRightmost:bool          = False
    debug_showDebugMenu         : bool          = True
    debug_showMemoryIndicator   : bool          = True
    debug_showDirtyCommitsAfterRefresh : bool   = True


@dataclass
class History(BasePrefs):
    filename = "history.json"

    openFileDialogLastPath      : str           = ""
    history                     : list[str]     = field(default_factory=list)
    nicknames                   : dict          = field(default_factory=dict)

    def addRepo(self, path):
        path = os.path.normpath(path)
        try:
            self.history.remove(path)
        except ValueError:
            pass
        self.history.append(path)
        self.write()

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

    def clear(self):
        self.history.clear()
        self.nicknames.clear()
        self.write()


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

