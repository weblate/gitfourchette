from typing import List, Dict
from PySide2.QtGui import *
from PySide2.QtCore import *
import os
import json
from dataclasses import dataclass, field

VERSION = "0.1-preview"

PROGRAM_NAME = "GitFourchette🅪"

QCoreApplication.setApplicationVersion(VERSION)
QCoreApplication.setApplicationName("GitFourchette")  # used by QStandardPaths
#QCoreApplication.setOrganizationName("GitFourchette")


prefsDir = QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation)


TOPO_ORDER = True  # false: experimental
MAX_LANES = 32
FLATTEN_LANES = False
FORCE_NEW_LANES_RIGHTMOST = False  # experimental
DEBUGRECTS = False


KEYS_ACCEPT = [Qt.Key_Enter, Qt.Key_Return]  # Enter = on keypad; Return = main keys
KEYS_REJECT = [Qt.Key_Delete, Qt.Key_Backspace]


SHORT_DATE_PRESETS = {
    'ISO': '%Y-%m-%d %H:%M',
    'd/m/y': '%d/%m/%y %H:%M',
    'd-m-y': '%d-%m-%y %H:%M',
    'd.m.y': '%d.%m.%y %H:%M',
    'm/d/y': '%m/%d/%y %I:%M %p',
    'Euro': '%a %d %b %Y %H:%M',
    'US': '%a, %b %d, %Y %I:%M %p'
}


def encodeBinary(b: QByteArray) -> str:
    return b.toBase64().data().decode('utf-8')


def decodeBinary(encoded: str) -> QByteArray:
    return QByteArray.fromBase64(encoded.encode('utf-8'))


class BasePrefs:
    def write(self):
        os.makedirs(prefsDir, exist_ok=True)
        prefsPath = os.path.join(prefsDir, getattr(self, 'filename'))
        with open(prefsPath, 'w') as f:
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
                if type(obj[k]) != type(self.__dict__[k]):
                    print(F"{prefsPath}: value type mismatch for {k}: expected {type(obj[k])}, got {type(self.__dict__[k])}")
                    continue
                self.__dict__[k] = obj[k]
        return True


@dataclass
class Prefs(BasePrefs):
    filename = "prefs.json"

    shortHashChars              : int           = 7
    splitterHandleWidth         : int           = -1
    shortTimeFormat             : str           = "%Y-%m-%d %H:%M"
    longTimeFormat              : str           = "%c"
    shortenDirectoryNames       : bool          = True
    showStatusBar               : bool          = True
    diff_tabSpaces              : int           = 4
    diff_largeFileThreshold     : int           = 300000
    diff_showStrayCRs           : bool          = True
    tabs_closeButton            : bool          = True
    tabs_expanding              : bool          = True
    tabs_autoHide               : bool          = False
    tabs_mergeWithMenubar       : bool          = True
    graph_lineHeight            : float         = 1.0
    debug_showDebugMenu         : bool          = True
    debug_showMemoryIndicator   : bool          = True


@dataclass
class History(BasePrefs):
    filename = "history.json"

    openFileDialogLastPath      : str           = ""
    history                     : List[str]     = field(default_factory=list)
    nicknames                   : Dict          = field(default_factory=dict)

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

    tabs                        : List[str]     = field(default_factory=list)
    activeTabIndex              : int           = -1
    windowGeometry              : str           = ""
    splitterStates              : Dict          = field(default_factory=dict)


prefs = Prefs()
prefs.load()

history = History()
history.load()

monoFont = QFontDatabase.systemFont(QFontDatabase.FixedFont)
monoFont.setPointSize(9)
monoFontMetrics = QFontMetrics(monoFont)

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
