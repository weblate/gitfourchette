from gitfourchette import log
from gitfourchette import util
from gitfourchette.qt import *
from pygit2 import Oid
from typing import ClassVar
import dataclasses
import enum


TAG = "nav"
BLANK_OID = Oid(raw=b'')


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
    diffScroll: int = 0
    diffCursor: int = 0

    URL_AUTHORITY: ClassVar[str] = "go"

    def __post_init__(self):
        assert isinstance(self.context, NavContext)
        assert isinstance(self.commit, Oid)
        assert isinstance(self.path, str)

    def __bool__(self):
        # A position is considered empty iff it has an empty context.
        # The locator is NOT considered empty when the path is empty but the context isn't
        # (e.g. in the STAGED context, with no files selected.)
        return self.context.value != NavContext.EMPTY
    
    def __repr__(self) -> str:
        return F"NavPos({self.contextKey[:10]} {self.path} {self.diffScroll} {self.diffCursor})"

    def similarEnoughTo(self, other: 'NavLocator'):
        return (self.context == other.context
                and self.commit == other.commit
                and self.path == other.path)

    def inSameDiffSetAs(self, other: 'NavLocator'):
        if self.context.isWorkdir():
            return other.context.isWorkdir()
        else:
            return self.commit == other.commit

    def asTitle(self):
        header = self.path
        if self.context == NavContext.COMMITTED:
            header += " @ " + util.shortHash(self.commit)
        elif self.context.isWorkdir():
            header += " [" + self.context.translateName() + "]"
        return header

    def url(self, *queryTuples: tuple[str, str]):
        url = QUrl()
        url.setScheme(APP_URL_SCHEME)
        url.setAuthority(NavLocator.URL_AUTHORITY)
        url.setPath("/" + self.path)

        if self.context == NavContext.COMMITTED:
            url.setFragment(self.commit.hex)
        else:
            url.setFragment(self.context.name)

        if queryTuples:
            query = QUrlQuery()
            query.setQueryItems(queryTuples)
            url.setQuery(query)

        return url

    def replace(self, **kwargs):
        return dataclasses.replace(self, **kwargs)

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
        return NavLocator(context, commit, path)

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

    def __init__(self):
        self.history = []
        self.recent = {}
        self.current = 0

    def push(self, pos: NavLocator):
        if not pos:
            return

        self.recent[pos.contextKey] = pos
        self.recent[pos.fileKey] = pos
        if pos.context.isWorkdir():
            self.recent["WORKDIR"] = pos

        if len(self.history) > 0 and self.history[self.current].similarEnoughTo(pos):
            # Update in-place
            self.history[self.current] = pos
        else:
            if self.current < len(self.history) - 1:
                self.trim()
            self.history.append(pos)
            self.current = len(self.history) - 1

    def trim(self):
        self.history = self.history[: self.current + 1]
        assert not self.canGoForward()

    def recallWorkdir(self):
        return self.recent.get("WORKDIR", None)

    def refine(self, locator: NavLocator):
        # If no path is specified, attempt to recall any path in the same context
        if not locator.path:
            locator2 = self.recent.get(locator.contextKey, None)
            if not locator2:
                return locator
            else:
                locator = locator2

        return self.recent.get(locator.fileKey, None) or locator

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

