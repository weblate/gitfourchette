import enum

from allqt import *
from dataclasses import dataclass, field
import json
import os

VERSION = "0.1-preview"

PROGRAM_NAME = "GitFourchette"

QCoreApplication.setApplicationVersion(VERSION)
QCoreApplication.setApplicationName("GitFourchette")  # used by QStandardPaths
#QCoreApplication.setOrganizationName("GitFourchette")


prefsDir = QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation)


KEYS_ACCEPT = [Qt.Key_Enter, Qt.Key_Return]  # Enter = on keypad; Return = main keys
KEYS_REJECT = [Qt.Key_Delete, Qt.Key_Backspace]


SHORT_DATE_PRESETS = [
    ('ISO', '%Y-%m-%d %H:%M'),
    ('Universal', '%d %b %Y %H:%M'),
    ('European', '%d/%m/%Y %H:%M'),
    ('American', '%m/%d/%Y %I:%M %p'),
]

# Don't use %Z (capital Z) for the named timezones, we can't get them from git.
# However, timezone offsets (%z) work fine.
LONG_DATE_PRESETS = [
    ("Full", "%c %z")
]


def encodeBinary(b: QByteArray) -> str:
    return b.toBase64().data().decode('utf-8')


def decodeBinary(encoded: str) -> QByteArray:
    return QByteArray.fromBase64(encoded.encode('utf-8'))


class BasePrefs:
    def write(self):
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

import enum
class PathDisplayStyle(enum.IntEnum):
    FULL_PATHS = 1,
    ABBREVIATE_DIRECTORIES = 2,
    SHOW_FILENAME_ONLY = 3,


@dataclass
class Prefs(BasePrefs):
    filename = "prefs.json"

    qtStyle                     : str           = ""
    shortHashChars              : int           = 7
    splitterHandleWidth         : int           = -1
    shortTimeFormat             : str           = SHORT_DATE_PRESETS[0][1]
    longTimeFormat              : str           = LONG_DATE_PRESETS[0][1]
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
    graph_rowHeightPercent      : int           = 100
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
        try:
            self.history.remove(path)
        except ValueError:
            pass
        self.history.append(path)
        self.write()

    def getRepoNickname(self, path):
        if path in self.nicknames:
            return self.nicknames[path]
        else:
            return os.path.basename(path)

    def setRepoNickname(self, path: str, nickname: str):
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
        self.history.remove(path)
        self.write()


@dataclass
class Session(BasePrefs):
    filename = "session.json"

    tabs                        : list[str]     = field(default_factory=list)
    activeTabIndex              : int           = -1
    windowGeometry              : str           = ""
    splitterStates              : dict          = field(default_factory=dict)


prefs = Prefs()
prefs.load()

history = History()
history.load()

monoFont = QFontDatabase.systemFont(QFontDatabase.FixedFont)
monoFont.setPointSize(9)
if prefs.diff_font:
    monoFont.fromString(prefs.diff_font)
monoFontMetrics = QFontMetricsF(monoFont)

alternateFont = QFont()
alternateFont.setItalic(True)

boldFont = QFont()
boldFont.setBold(True)

smallFont = QFont()
smallFont.setWeight(QFont.Light)
#smallFont.setPointSize(9)
smallFontMetrics = QFontMetrics(smallFont)

statusIcons = {}
for status in "ACDMRTUX":
    statusIcons[status] = QIcon(F"icons/status_{status.lower()}.svg")

# Note: if icons don't show up, you may need to install the 'qt6-svg' package
