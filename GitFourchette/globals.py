from typing import List
from PySide2.QtGui import *
from PySide2.QtCore import *
import os

TAB_SPACES = 4

VERSION = "0.1-preview"

PROGRAM_NAME = "GitFourchette🅪"

monoFont = QFontDatabase.systemFont(QFontDatabase.FixedFont)
monoFont.setPointSize(9)
monoFontMetrics = QFontMetrics(monoFont)

alternateFont = QFontDatabase.systemFont(QFontDatabase.GeneralFont)
alternateFont.setItalic(True)

smallFont = QFontDatabase.systemFont(QFontDatabase.GeneralFont)
smallFont.setWeight(QFont.Light)
smallFont.setPointSize(9)
smallFontMetrics = QFontMetrics(smallFont)

statusIcons = {}
for status in "ACDMRTUX":
    statusIcons[status] = QIcon(F"icons/status_{status.lower()}.svg")


appSettings = QSettings('GitFourchette', 'GitFourchette')


# for open dialog
SK_LAST_OPEN = "last_open"



def getValueAndWriteDefault(key, defaultValue):
    if appSettings.contains(key):
        return appSettings.value(key, defaultValue)
    else:
        appSettings.setValue(key, defaultValue)
        return defaultValue


graphViewTimeFormat = getValueAndWriteDefault("GraphView/TimeFormat", "%d-%m-%y %H:%M")
splitterHandleWidth = int(getValueAndWriteDefault("SplitterHandleWidth", -1))
shortHashChars = int(getValueAndWriteDefault("ShortHashChars", 7))


def getRepoHistory() -> List[str]:
    history : List[str] = []
    size = appSettings.beginReadArray("RepoHistory")
    for i in range(0, size):
        appSettings.setArrayIndex(i)
        history.append(str(appSettings.value("Path")))
    appSettings.endArray()
    return history


def addRepoToHistory(repoDir):
    history: List[str] = getRepoHistory()
    try:
        history.remove(repoDir)
    except ValueError:
        pass
    history.insert(0, repoDir)
    appSettings.beginWriteArray("RepoHistory", len(history))
    for i, value in enumerate(history):
        appSettings.setArrayIndex(i)
        appSettings.setValue("Path", value)
    appSettings.endArray()


def getRepoNickname(repoDir):
    key = repoDir.replace('/', '.')
    return appSettings.value("RepoNicknames/" + key, None) or os.path.basename(repoDir)


def setRepoNickname(repoDir, nickname):
    key = repoDir.replace('/', '.')
    appSettings.setValue("RepoNicknames/" + key, nickname)
