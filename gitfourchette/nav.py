from __future__ import annotations
from gitfourchette import log
from gitfourchette.qt import *
from gitfourchette.toolbox import *
from pygit2 import Oid
from typing import ClassVar
import dataclasses
import enum
import time


TAG = "nav"
BLANK_OID = Oid(raw=b'')
PUSH_INTERVAL = 0.5


class NavFlags(enum.IntFlag):
    IgnoreInvalidLocation = enum.auto()
    ForceRefreshWorkdir = enum.auto()
    AllowWriteIndex = enum.auto()
    AllowLongLines = enum.auto()
    AllowLargeDiffs = enum.auto()

    DefaultFlags = 0

    @staticmethod
    def parseUrl(url: QUrl):
        query = QUrlQuery(url)
        value = query.queryItemValue("jumpflags")

        if value:
            return NavFlags(int(value))
        else:
            return NavFlags.DefaultFlags


@enum.unique
class NavContext(enum.IntEnum):
    """
    State of a patch in the staging pipeline
    """

    EMPTY       = 0
    COMMITTED   = 1
    WORKDIR     = 2
    UNTRACKED   = 3
    UNSTAGED    = 4
    STAGED      = 5

    def isWorkdir(self):
        return self == NavContext.WORKDIR or self == NavContext.UNTRACKED or self == NavContext.UNSTAGED or self == NavContext.STAGED

    def isDirty(self):
        return self == NavContext.UNTRACKED or self == NavContext.UNSTAGED

    def allowsRawFileAccess(self):
        return self != NavContext.COMMITTED

    def translateName(self):
        names = {
            NavContext.EMPTY: translate("NavContext", "Empty"),
            NavContext.UNTRACKED: translate("NavContext", "Untracked"),
            NavContext.UNSTAGED: translate("NavContext", "Unstaged"),
            NavContext.STAGED: translate("NavContext", "Staged"),
            NavContext.COMMITTED: translate("NavContext", "Committed"),
        }
        return names.get(self, translate("NavContext", "Unknown"))


@dataclasses.dataclass(frozen=True)
class NavLocator:
    """
    Resource locator within a repository.
    Used to navigate the UI to a specific area of a repository.
    """

    context: NavContext = NavContext.EMPTY
    commit: Oid = BLANK_OID
    path: str = ""
    diffLineNo: int = 0
    diffCursor: int = 0
    diffScroll: int = 0
    diffScrollTop: int = 0
    flags: NavFlags = NavFlags.DefaultFlags  # WARNING: Those are not saved in history

    URL_AUTHORITY: ClassVar[str] = "jump"

    def __post_init__(self):
        assert isinstance(self.context, NavContext)
        assert isinstance(self.commit, Oid)
        assert isinstance(self.path, str)

    def __bool__(self):
        """
        Return True if the locator's context is anything but EMPTY.

        The locator is NOT considered empty when the path is empty but the context isn't
        (e.g. in the STAGED context, with no files selected.)
        """
        return self.context.value != NavContext.EMPTY
    
    def __repr__(self) -> str:
        return F"{self.__class__.__name__}({self.contextKey[:10]} {self.path})"

    @staticmethod
    def inCommit(oid: Oid, path: str = ""):
        return NavLocator(context=NavContext.COMMITTED, commit=oid, path=path)

    @staticmethod
    def inUnstaged(path: str = ""):
        return NavLocator(context=NavContext.UNSTAGED, path=path)

    @staticmethod
    def inStaged(path: str = ""):
        return NavLocator(context=NavContext.STAGED, path=path)

    def isSimilarEnoughTo(self, other: NavLocator):
        """Coarse equality - Compare context, commit & path (ignores flags & position in diff)"""
        return (self.context == other.context
                and self.commit == other.commit
                and self.path == other.path)

    def isInSameDiffSetAs(self, other: NavLocator):
        if self.context.isWorkdir():
            return other.context.isWorkdir()
        else:
            return self.commit == other.commit

    def hasFlags(self, flags: NavFlags):
        return flags == (self.flags & flags)

    def asTitle(self):
        header = self.path
        if self.context == NavContext.COMMITTED:
            header += " @ " + shortHash(self.commit)
        elif self.context.isWorkdir():
            header += " [" + self.context.translateName() + "]"
        return header

    def url(self):
        url = QUrl()
        url.setScheme(APP_URL_SCHEME)
        url.setAuthority(NavLocator.URL_AUTHORITY)
        url.setPath("/" + self.path)

        if self.context == NavContext.COMMITTED:
            url.setFragment(self.commit.hex)
        else:
            url.setFragment(self.context.name)

        query = QUrlQuery()
        if self.flags != NavFlags.DefaultFlags:
            query.addQueryItem("flags", str(self.flags.value))
        if not query.isEmpty():
            url.setQuery(query)

        return url

    def toHtml(self, text: str):
        href = self.url().toString()
        assert '"' not in href
        if "[" in text:
            return text.replace("[", f"<a href=\"{href}\">").replace("]", "</a>")
        else:
            return f"<a href=\"{href}\">{text}</a>"

    def replace(self, **kwargs) -> NavLocator:
        return dataclasses.replace(self, **kwargs)

    def coarse(self, keepFlags=False):
        return NavLocator(context=self.context, commit=self.commit, path=self.path)

    def withExtraFlags(self, extraFlags: NavFlags) -> NavLocator:
        return self.replace(flags=self.flags | extraFlags)

    @staticmethod
    def parseUrl(url: QUrl):
        assert url.authority() == NavLocator.URL_AUTHORITY
        assert url.hasFragment()
        frag = url.fragment()
        path = url.path()
        assert path.startswith("/")
        path = path.removeprefix("/")
        try:
            context = NavContext[frag]
            commit = BLANK_OID
        except KeyError:
            context = NavContext.COMMITTED
            commit = Oid(hex=frag)

        flags = NavFlags.DefaultFlags
        query = QUrlQuery(url.query())
        if not query.isEmpty():
            strFlags = query.queryItemValue("flags")
            flags = NavFlags(int(strFlags))

        return NavLocator(context, commit, path, flags=flags)

    @property
    def contextKey(self):
        if self.context == NavContext.COMMITTED:
            return self.commit.hex
        else:
            return self.context.name

    @property
    def fileKey(self):
        """ For NavHistory.recallFileInContext(). """
        return f"{self.contextKey}:{self.path}"


class NavHistory:
    """
    History of the files that the user has viewed in a repository's commit log and workdir.
    """

    history: list[NavLocator]
    "Stack of position snapshots."

    current: int
    "Current position in the history stack. Hitting next/forward moves this index."

    recent: dict[str, NavLocator]
    "Most recent NavPos by context key"

    lastPushTime: float
    """Timestamp of the last modification to the history,
    to avoid pushing a million entries when dragging the mouse, etc."""

    def __init__(self):
        self.history = []
        self.recent = {}
        self.current = 0
        self.lastPushTime = 0.0
        self.ignoreDelay = False

        # In a real use case, locators are dropped from the history if push()
        # calls occur in quick succession. This avoids polluting the history
        # with unimportant entries when the user drags the mouse across
        # GraphView, for instance. However, in unit tests, navigation occurs
        # blazingly quickly, but we want each location to be recorded in the
        # history.
        from gitfourchette.settings import TEST_MODE
        self.ignoreDelay |= TEST_MODE

    def push(self, pos: NavLocator):
        if not pos:
            return

        # Clear volatile flags
        if pos.flags != NavFlags.DefaultFlags:
            pos = pos.replace(flags=NavFlags.DefaultFlags)

        self.recent[pos.contextKey] = pos
        self.recent[pos.fileKey] = pos
        if pos.context.isWorkdir():
            self.recent["WORKDIR"] = pos

        now = time.time()
        if self.ignoreDelay:
            recentPush = False
        else:
            recentPush = (now - self.lastPushTime) < PUSH_INTERVAL

        if len(self.history) > 0 and \
                (recentPush or self.history[self.current].isSimilarEnoughTo(pos)):
            # Update in-place; don't update lastPush timestamp
            self.history[self.current] = pos
        else:
            if self.current < len(self.history) - 1:
                self.trim()
            self.history.append(pos)
            self.current = len(self.history) - 1
            self.lastPushTime = now

    def trim(self):
        self.history = self.history[: self.current + 1]
        assert not self.canGoForward()

    def recallWorkdir(self):
        """
        Attempt to return the most recent locator matching STAGED or UNSTAGED
        contexts.

        May return None there's no trace of the workdir in the history.
        """
        return self.recent.get("WORKDIR", None)

    def refine(self, locator: NavLocator):
        """
        Attempt to make a locator more precise by looking up the most recent
        matching locator in the history.

        For example, given a locator with context=UNSTAGED but without a path,
        refine() will return the locator for an unstaged file that was most
        recently saved to the history.

        In addition, diff cursor/scroll positions will be filled in if the
        history contains them.

        If refining isn't possible, this function returns the same locator as
        the input.
        """

        originalLocator = locator

        # If no path is specified, attempt to recall any path in the same context
        if not locator.path:
            locator = self.recent.get(locator.contextKey, None)
            if not locator:
                locator = originalLocator

        locator = self.recent.get(locator.fileKey, None) or locator

        # Restore volatile flags
        if originalLocator.flags != locator.flags:
            locator = locator.replace(flags=originalLocator.flags)

        return locator

    def canGoForward(self):
        count = len(self.history)
        return count > 0 and self.current < count - 1

    def canGoBack(self):
        count = len(self.history)
        return count > 0 and self.current > 0

    def canGoDelta(self, delta: int):
        assert delta == -1 or delta == 1
        if delta > 0:
            return self.canGoForward()
        else:
            return self.canGoBack()

    def navigateBack(self):
        if not self.canGoBack():
            return None
        self.current -= 1
        return self.history[self.current]

    def navigateForward(self):
        if not self.canGoForward():
            return None
        self.current += 1
        return self.history[self.current]

    def navigateDelta(self, delta: int):
        assert delta == -1 or delta == 1
        if delta > 0:
            return self.navigateForward()
        else:
            return self.navigateBack()

    def popCurrent(self):
        if self.current < len(self.history):
            return self.history.pop(self.current)
        else:
            return None

    def getTextLog(self):
        s = "------------ NAV LOG ------------"
        i = len(self.history) - 1
        for h in reversed(self.history):
            s += "\n"
            if i == self.current:
                s += "---> "
            else:
                s += "     "
            s += f"{h.contextKey[:7]} {h.path:32} {h.diffScroll} {h.diffCursor}"
            i -= 1
        return s

