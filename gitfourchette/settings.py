from contextlib import suppress
import dataclasses
import enum
import logging
import os
import shlex
import sys

from gitfourchette import pycompat  # StrEnum for Python 3.10
from gitfourchette.prefsfile import PrefsFile
from gitfourchette.qt import *
from gitfourchette.toolbox.benchmark import BENCHMARK_LOGGING_LEVEL
from gitfourchette.toolbox.gitutils import AuthorDisplayStyle
from gitfourchette.toolbox.pathutils import PathDisplayStyle

logger = logging.getLogger(__name__)

TEST_MODE = "pytest" in sys.modules
"""
Unit testing mode (don't touch real user prefs, etc.).
Can be forced with command-line switch "--test-mode".
"""

DEVDEBUG = TEST_MODE
"""
Enable expensive assertions and debugging features.
Can be forced with command-line switch "--debug".
"""

SYNC_TASKS = False
"""
Force tasks to run synchronously on the UI thread.
Useful for debugging.
Can be forced with command-line switch "--no-threads".
"""

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
    "Beyond Compare": "bcompare $L $R",
    "FileMerge": "opendiff $L $R",
    "GVim": "gvim -f -d $L $R",
    "JetBrains CLion": "clion diff $L $R",
    "JetBrains IDEA": "idea diff $L $R",
    "JetBrains PyCharm": "pycharm diff $L $R",
    "KDiff3": "kdiff3 $L $R",
    "MacVim": "mvim -f -d $L $R",
    "Meld": "meld $L $R",
    "P4Merge": "p4merge $L $R",
    "SourceGear DiffMerge": "diffmerge $L $R",
    "Visual Studio Code": "code --new-window --wait --diff $L $R",
    "WinMerge": "winmergeu /u /wl /wr $L $R",
}

# $B: ANCESTOR/BASE/CENTER
# $L: OURS/LOCAL/LEFT
# $R: THEIRS/REMOTE/RIGHT
# $M: MERGED/OUTPUT
MERGE_TOOL_PRESETS = {
    "Beyond Compare": "bcompare $L $R $B $M",
    "FileMerge": "opendiff -ancestor $B $L $R -merge $M",
    "GVim": "gvim -f -d -c 'wincmd J' $M $L $B $R",
    "Helix P4Merge": "p4merge $B $L $R $M",
    "JetBrains CLion": "clion merge $L $R $B $M",
    "JetBrains IDEA": "idea merge $L $R $B $M",
    "JetBrains PyCharm": "pycharm merge $L $R $B $M",
    "KDiff3": "kdiff3 --merge $B $L $R --output $M",
    "MacVim": "mvim -f -d -c 'wincmd J' $M $L $B $R",
    "Meld": "meld --auto-merge $B $L $R --output=$M",
    "SourceGear DiffMerge": "diffmerge --merge --result=$M $L $B $R",
    "Visual Studio Code": "code --new-window --wait --merge $L $R $B $M",
    "WinMerge": "winmergeu /u /wl /wm /wr /am $B $L $R /o $M",
}


DEFAULT_DIFF_TOOL_PRESET = ""
DEFAULT_MERGE_TOOL_PRESET = ""


def _filterToolPresets():  # pragma: no cover
    freedesktopTools = ["Kate", "KWrite"]
    macTools = ["FileMerge", "MacVim", "BBEdit"]
    winTools = ["WinMerge"]

    global DEFAULT_MERGE_TOOL_PRESET
    global DEFAULT_DIFF_TOOL_PRESET

    if MACOS:
        excludeTools = winTools + freedesktopTools
        DEFAULT_DIFF_TOOL_PRESET = "FileMerge"
        DEFAULT_MERGE_TOOL_PRESET = "FileMerge"
    elif WINDOWS:
        excludeTools = macTools + freedesktopTools
        DEFAULT_DIFF_TOOL_PRESET = "WinMerge"
        DEFAULT_MERGE_TOOL_PRESET = "WinMerge"
    else:
        excludeTools = macTools + winTools
        DEFAULT_DIFF_TOOL_PRESET = "KDiff3"
        DEFAULT_MERGE_TOOL_PRESET = "KDiff3"

    for key in excludeTools:
        with suppress(KeyError):
            del EDITOR_TOOL_PRESETS[key]
        with suppress(KeyError):
            del DIFF_TOOL_PRESETS[key]
        with suppress(KeyError):
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


class LoggingLevel(enum.IntEnum):
    BENCHMARK = BENCHMARK_LOGGING_LEVEL
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
    authorDisplayStyle          : AuthorDisplayStyle = AuthorDisplayStyle.FULL_NAME
    maxRecentRepos              : int           = 20
    showStatusBar               : bool          = True
    autoHideMenuBar             : bool          = False
    diff_font                   : str           = ""
    diff_tabSpaces              : int           = 4
    diff_largeFileThresholdKB   : int           = 512
    diff_imageFileThresholdKB   : int           = 5000
    diff_wordWrap               : bool          = False
    diff_showStrayCRs           : bool          = True
    diff_colorblind             : bool          = False
    tabs_closeButton            : bool          = True
    tabs_expanding              : bool          = True
    tabs_autoHide               : bool          = False
    tabs_doubleClickOpensFolder : bool          = True
    graph_chronologicalOrder    : bool          = True
    graph_rowHeight             : GraphRowHeight= GraphRowHeight.RELAXED
    graph_flattenLanes          : bool          = True
    graph_authorDiffAsterisk    : bool          = True
    external_editor             : str           = ""
    external_diff               : str           = DIFF_TOOL_PRESETS[DEFAULT_DIFF_TOOL_PRESET]
    external_merge              : str           = MERGE_TOOL_PRESETS[DEFAULT_MERGE_TOOL_PRESET]
    trash_maxFiles              : int           = 250
    trash_maxFileSizeKB         : int           = 1024
    debug_smoothScroll          : bool          = True
    debug_hideStashJunkParents  : bool          = True
    debug_autoRefresh           : bool          = True
    debug_modalSidebar          : bool          = False
    debug_taskClicks            : bool          = False
    debug_verbosity             : LoggingLevel  = LoggingLevel.WARNING
    debug_forceQtApi            : QtApiNames    = QtApiNames.QTAPI_AUTOMATIC

    @property
    def listViewScrollMode(self) -> QAbstractItemView.ScrollMode:
        if self.debug_smoothScroll:
            return QAbstractItemView.ScrollMode.ScrollPerPixel
        else:
            return QAbstractItemView.ScrollMode.ScrollPerItem


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
            repo.pop('superproject', None)

    def getRepoTabName(self, path: str):
        name = self.getRepoNickname(path)

        seen = {path}
        while path:
            path = self.getRepoSuperproject(path)
            if path:
                if path in seen:
                    logger.warning(f"Circular superproject in {self._filename}! {path}")
                    return name
                seen.add(path)
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
    splitterSizes               : dict          = dataclasses.field(default_factory=dict)


# Initialize default prefs and history.
# The app should load the user's prefs with prefs.load() and history.load().
prefs = Prefs()
history = History()


def qtIsNativeMacosStyle():  # pragma: no cover
    if not MACOS:
        return False
    return (not prefs.qtStyle) or (prefs.qtStyle.lower() == "macos")


def _getCmdName(command, fallback, presets):
    if not command.strip():
        return fallback

    presetName = next((k for k, v in presets.items() if v == command), "")
    if presetName:
        return presetName

    tokens = shlex.split(command, posix=not WINDOWS)

    try:
        p = tokens[0]
        p = p.removeprefix('"').removeprefix("'")
        p = p.removesuffix('"').removesuffix("'")
        p = os.path.basename(p)

        return p
    except IndexError:
        return fallback


def getExternalEditorName():
    return _getCmdName(prefs.external_editor, tr("Text Editor"), EDITOR_TOOL_PRESETS)


def getDiffToolName():
    return _getCmdName(prefs.external_diff, tr("Diff Tool"), DIFF_TOOL_PRESETS)


def getMergeToolName():
    return _getCmdName(prefs.external_merge, tr("Merge Tool"), MERGE_TOOL_PRESETS)
