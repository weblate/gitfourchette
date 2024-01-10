import contextlib
import dataclasses
import enum
import logging
import os
import shlex

from gitfourchette import pycompat  # StrEnum for Python 3.10
from gitfourchette.prefsfile import PrefsFile
from gitfourchette.qt import *
from gitfourchette.toolbox.gitutils import AuthorDisplayStyle
from gitfourchette.toolbox.pathutils import PathDisplayStyle
from gitfourchette.trtables import TrTables

logger = logging.getLogger(__name__)

TEST_MODE = False
""" Unit testing mode. """

SYNC_TASKS = False
""" Force tasks to run synchronously on the UI thread. """

LANGUAGES = [
    "en_US",
    "fr_FR",
]

SHORT_DATE_PRESETS = {
    "ISO": "yyyy-MM-dd HH:mm",
    "Universal 1": "dd MMM yyyy HH:mm",
    "Universal 2": "ddd dd MMM yyyy HH:mm",
    "European 1": "dd/MM/yy HH:mm",
    "European 2": "dd.MM.yy HH:mm",
    "American": "M/d/yy h:mm ap",
}

EDITOR_TOOL_PRESETS = {
    "System default": "",
    "BBEdit": "bbedit",
    "GVim": "gvim",
    "KWrite": "kwrite",
    "Kate": "kate",
    "MacVim": "mvim",
    "Visual Studio Code": "code",
}

DIFF_TOOL_PRESETS = {
    "Beyond Compare": "bcompare $1 $2",
    "FileMerge": "opendiff $1 $2",
    "GVim": "gvim -f -d $1 $2",
    "JetBrains CLion": "clion diff $1 $2",
    "JetBrains IDEA": "idea diff $1 $2",
    "JetBrains PyCharm": "pycharm diff $1 $2",
    "KDiff3": "kdiff3 $1 $2",
    "MacVim": "mvim -f -d $1 $2",
    "Meld": "meld $1 $2",
    "P4Merge": "p4merge $1 $2",
    "SourceGear DiffMerge": "diffmerge $1 $2",
    "Visual Studio Code": "code --diff $1 $2 --wait",
    "WinMerge": "winmergeu /u /wl /wr $1 $2",
}

# $1: ANCESTOR/BASE
# $2: OURS/LOCAL
# $3: THEIRS/REMOTE
# $4: MERGED
MERGE_TOOL_PRESETS = {
    "Beyond Compare": "bcompare $1 $2 $3 $4",
    "FileMerge": "opendiff -ancestor $1 $2 $3 -merge $4",
    "GVim": "gvim -f -d -c 'wincmd J' $4 $2 $1 $3",
    "Helix P4Merge": "p4merge $1 $2 $3 $4",
    "JetBrains CLion": "clion merge $2 $3 $1 $4",
    "JetBrains IDEA": "idea merge $2 $3 $1 $4",
    "JetBrains PyCharm": "pycharm merge $2 $3 $1 $4",
    "KDiff3": "kdiff3 --merge $1 $2 $3 --output $4",
    "MacVim": "mvim -f -d -c 'wincmd J' $4 $2 $1 $3",
    "Meld": "meld --auto-merge $1 $2 $3 -o $4",
    "SourceGear DiffMerge": "diffmerge --merge --result $4 $1 $2 $3",
    "Visual Studio Code": "code --merge $2 $3 $1 $4 --wait",
    "WinMerge": "winmergeu /u /wl /wm /wr /am $1 $2 $3 /o $4",
}


def _filterToolPresets():
    freedesktopTools = ["Kate", "KWrite"]
    macTools = ["FileMerge", "MacVim", "BBEdit"]
    winTools = ["WinMerge"]

    if MACOS:
        excludeTools = winTools + freedesktopTools
    elif WINDOWS:
        excludeTools = macTools + freedesktopTools
    else:
        excludeTools = macTools + winTools

    for key in excludeTools:
        with contextlib.suppress(KeyError):
            del DIFF_TOOL_PRESETS[key]
        with contextlib.suppress(KeyError):
            del DIFF_TOOL_PRESETS[key]
        with contextlib.suppress(KeyError):
            del MERGE_TOOL_PRESETS[key]


_filterToolPresets()
del _filterToolPresets


class GraphRowHeight(enum.IntEnum):
    CRAMPED = 80
    TIGHT = 100
    RELAXED = 130
    ROOMY = 150
    SPACIOUS = 175


class QtApiNames(enum.StrEnum):
    QTAPI_AUTOMATIC = ""
    QTAPI_PYQT6 = "pyqt6"
    QTAPI_PYQT5 = "pyqt5"
    QTAPI_PYSIDE6 = "pyside6"
    QTAPI_PYSIDE2 = "pyside2"


class LoggingLevel(enum.IntEnum):
    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING


@dataclasses.dataclass
class Prefs(PrefsFile):
    _filename = "prefs.json"

    language                    : str           = ""
    qtStyle                     : str           = ""
    shortHashChars              : int           = 7
    shortTimeFormat             : str           = list(SHORT_DATE_PRESETS.values())[0]
    pathDisplayStyle            : PathDisplayStyle = PathDisplayStyle.FULL_PATHS
    authorDisplayStyle          : AuthorDisplayStyle = AuthorDisplayStyle.ABBREVIATED_EMAIL
    maxRecentRepos              : int           = 20
    showStatusBar               : bool          = True
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
    graph_rowHeight             : GraphRowHeight= GraphRowHeight.RELAXED
    graph_flattenLanes          : bool          = True
    graph_authorDiffAsterisk    : bool          = True
    external_editor             : str           = ""
    external_diff               : str           = list(DIFF_TOOL_PRESETS.values())[0]
    external_merge              : str           = list(MERGE_TOOL_PRESETS.values())[0]
    trash_maxFiles              : int           = 250
    trash_maxFileSizeKB         : int           = 1024
    debug_showMemoryIndicator   : bool          = True
    debug_showPID               : bool          = True
    debug_fixU2029InClipboard   : bool          = False
    debug_hideStashJunkParents  : bool          = True
    debug_autoRefresh           : bool          = True
    debug_modalSidebar          : bool          = False
    debug_verbosity             : LoggingLevel  = LoggingLevel.WARNING
    debug_forceQtApi            : QtApiNames    = QtApiNames.QTAPI_AUTOMATIC


@dataclasses.dataclass
class History(PrefsFile):
    _filename = "history.json"

    repos: dict = dataclasses.field(default_factory=dict)
    cloneHistory: list = dataclasses.field(default_factory=list)
    fileDialogPaths: dict = dataclasses.field(default_factory=dict)

    _maxSeq = -1

    def addRepo(self, path: str):
        path = os.path.normpath(path)
        repo = self.getRepo(path)
        repo['seq'] = self.drawSequenceNumber()
        return repo

    def getRepo(self, path: str) -> dict:
        path = os.path.normpath(path)
        try:
            repo = self.repos[path]
        except KeyError:
            repo = {}
            self.repos[path] = repo
        return repo

    def getRepoNickname(self, path):
        repo = self.getRepo(path)
        path = os.path.normpath(path)
        return repo.get("nickname", os.path.basename(path))

    def setRepoNickname(self, path: str, nickname: str):
        repo = self.getRepo(path)
        nickname = nickname.strip()
        if nickname:
            repo['nickname'] = nickname
        else:
            repo.pop('nickname', None)

    def getRepoNumCommits(self, path: str):
        repo = self.getRepo(path)
        return repo.get('length', 0)

    def setRepoNumCommits(self, path: str, commitCount: int):
        repo = self.getRepo(path)
        if commitCount > 0:
            repo['length'] = commitCount
        else:
            repo.pop('length', None)

    def getRepoSuperproject(self, path: str):
        repo = self.getRepo(path)
        return repo.get('superproject', "")

    def setRepoSuperproject(self, path: str, superprojectPath: str):
        repo = self.getRepo(path)
        if superprojectPath:
            repo['superproject'] = superprojectPath
        else:
            repo.pop('superprojectPath', None)

    def getRepoTabName(self, path: str):
        name = self.getRepoNickname(path)

        while path:
            path = self.getRepoSuperproject(path)
            if path:
                superprojectName = self.getRepoNickname(path)
                name = f"{superprojectName}: {name}"

        return name

    def removeRepo(self, path: str):
        path = os.path.normpath(path)
        self.repos.pop(path, None)
        self.invalidateSequenceNumber()

    def clearRepoHistory(self):
        self.repos.clear()
        self.invalidateSequenceNumber()

    def getRecentRepoPaths(self, n: int, newestFirst=True):
        sortedPaths = (path for path, _ in
                       sorted(self.repos.items(), key=lambda i: i[1].get('seq', -1), reverse=newestFirst))

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

    def drawSequenceNumber(self, increment=1):
        if self._maxSeq < 0 and self.repos:
            self._maxSeq = max(r.get('seq', -1) for r in self.repos.values())
        self._maxSeq += increment
        return self._maxSeq

    def invalidateSequenceNumber(self):
        self._maxSeq = -1


@dataclasses.dataclass
class Session(PrefsFile):
    _filename = "session.json"

    tabs                        : list          = dataclasses.field(default_factory=list)
    activeTabIndex              : int           = -1
    windowGeometry              : bytes         = b""
    splitterStates              : dict          = dataclasses.field(default_factory=dict)


# Initialize default prefs and history.
# The app should load the user's prefs with prefs.load() and history.load().
prefs = Prefs()
history = History()
installedTranslators = []


def qtIsNativeMacosStyle():
    if not MACOS:
        return False
    return (not prefs.qtStyle) or (prefs.qtStyle.lower() == "macos")


def applyQtStylePref(forceApplyDefault: bool):
    app = QApplication.instance() 

    if prefs.qtStyle:
        app.setStyle(prefs.qtStyle)
    elif forceApplyDefault:
        app.setStyle(app.PLATFORM_DEFAULT_STYLE_NAME)

    if MACOS:
        app.setAttribute(Qt.ApplicationAttribute.AA_DontShowIconsInMenus, qtIsNativeMacosStyle())


def applyLanguagePref():
    app = QCoreApplication.instance()

    # Flush old translators
    while installedTranslators:
        app.removeTranslator(installedTranslators.pop())

    if prefs.language:
        locale = QLocale(prefs.language)
    else:
        locale = QLocale()  # "Automatic" setting: Get system locale
    QLocale.setDefault(locale)

    newTranslator = QTranslator(app)
    if newTranslator.load(locale, "gitfourchette", "_", "assets:", ".qm"):
        app.installTranslator(newTranslator)
        installedTranslators.append(newTranslator)
    else:
        logger.warning("Failed to load translator.")
        newTranslator.deleteLater()

    # Load Qt base translation
    if not QT5:  # Do this on Qt 6 and up only
        try:
            baseTranslator = QTranslator(app)
            if baseTranslator.load(locale, "qtbase", "_", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
                app.installTranslator(baseTranslator)
                installedTranslators.append(baseTranslator)
            else:
                baseTranslator.deleteLater()
        except Exception as exc:
            logger.warning(f"Failed to load Qt base translation for language: {prefs.language}", exc_info=True)

    TrTables.retranslateAll()


def _getCmdName(command, fallback, presets):
    if not command.strip():
        return fallback
    else:
        presetName = next((k for k, v in presets.items() if v == command), "")
        if presetName:
            return presetName

        p = shlex.split(command, posix=not WINDOWS)[0]
        p = p.removeprefix('"').removeprefix("'")
        p = p.removesuffix('"').removesuffix("'")
        p = os.path.basename(p)
        return p


def getExternalEditorName():
    return _getCmdName(prefs.external_editor, tr("Text Editor"), EDITOR_TOOL_PRESETS)


def getDiffToolName():
    return _getCmdName(prefs.external_diff, tr("Diff Tool"), DIFF_TOOL_PRESETS)


def getMergeToolName():
    return _getCmdName(prefs.external_merge, tr("Merge Tool"), MERGE_TOOL_PRESETS)
