from typing import List
from PySide2.QtWidgets import *
from PySide2.QtGui import *
from PySide2.QtCore import *
import git
import os

TAB_SPACES = 4

VERSION = "0.1-preview"

PROGRAM_NAME = "GitFourchette🅪"

PROGRAM_ABOUT = F"""\
<h1>{PROGRAM_NAME}</h1>
Version {VERSION}
<p>
This is my git frontend.<br>There are many like it but this one is mine.
</p>
"""

monoFont = QFontDatabase.systemFont(QFontDatabase.FixedFont)


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
