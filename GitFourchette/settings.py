from typing import List, Dict
from PySide2.QtGui import *
from PySide2.QtCore import *
import os
import json
from pathlib import Path

VERSION = "0.1-preview"

PROGRAM_NAME = "GitFourchette🅪"

QCoreApplication.setApplicationVersion(VERSION)
QCoreApplication.setApplicationName("GitFourchette")  # used by QStandardPaths
#QCoreApplication.setOrganizationName("GitFourchette")


prefsDir = QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation)


def encodeBinary(b: QByteArray) -> str:
    return b.toBase64().data().decode('utf-8')


def decodeBinary(encoded: str) -> QByteArray:
    return QByteArray.fromBase64(encoded.encode('utf-8'))


class BasePrefs:
    def write(self):
        os.makedirs(prefsDir, exist_ok=True)
        prefsPath = Path(prefsDir) / getattr(self, 'filename')
        with open(prefsPath, 'w') as f:
            json.dump(self.__dict__, f, indent='\t')

    def load(self):
        prefsPath = QStandardPaths.locate(QStandardPaths.AppConfigLocation, getattr(self, 'filename'))
        if not prefsPath:  # couldn't be found
            return False
        with open(prefsPath, 'r') as f:
            obj = json.load(f)
            for k in obj:
                if k.startswith('_'):
                    continue
                self.__dict__[k] = obj[k]
                #print(F"{k} {type(obj[k])}")
        return True


class Prefs(BasePrefs):
    filename = "prefs.json"

    tabSize: int
    shortHashChars: int
    splitterHandleWidth: int
    shortTimeFormat: str
    shortenDirectoryNames: bool

    def __init__(self):
        self.tabSize = 4
        self.shortHashChars = 7
        self.splitterHandleWidth = -1
        self.shortTimeFormat = "%d-%m-%y %H:%M"
        self.shortenDirectoryNames = True


class History(BasePrefs):
    filename = "history.json"

    openFileDialogLastPath: str
    history: List[str]
    nicknames: Dict

    def __init__(self):
        self.openFileDialogLastPath = None
        self.history = []
        self.nicknames = {}

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

    def setRepoNickname(self, path, nickname):
        self.nicknames[path] = nickname
        self.write()


class Session(BasePrefs):
    filename = "session.json"

    tabs: List[str]
    activeTabIndex: int
    windowGeometry: str
    splitterStates: Dict


prefs = Prefs()
prefs.load()

history = History()
history.load()

monoFont = QFontDatabase.systemFont(QFontDatabase.FixedFont)
monoFont.setPointSize(9)
monoFontMetrics = QFontMetrics(monoFont)

alternateFont = QFont()
alternateFont.setItalic(True)

smallFont = QFont()
smallFont.setWeight(QFont.Light)
#smallFont.setPointSize(9)
smallFontMetrics = QFontMetrics(smallFont)

statusIcons = {}
for status in "ACDMRTUX":
    statusIcons[status] = QIcon(F"icons/status_{status.lower()}.svg")
