from dataclasses import dataclass
from gitfourchette import log
from gitfourchette import util
from gitfourchette.qt import *
from pygit2 import Oid
import enum


BLANK_OID = Oid(raw=b'')


@enum.unique
class NavContext(enum.IntEnum):
    """
    State of a patch in the staging pipeline
    """

    EMPTY = 0
    UNTRACKED = 1
    UNSTAGED = 2
    STAGED = 3
    COMMITTED = 4

    def isWorkdir(self):
        return self == NavContext.UNTRACKED or self == NavContext.UNSTAGED or self == NavContext.STAGED

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


@dataclass(frozen=True)
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

    def asTitle(self):
        header = self.path
        if self.context == NavContext.COMMITTED:
            header += " @ " + util.shortHash(self.commit)
        elif self.context.isWorkdir():
            header += " [" + self.context.translateName() + "]"
        return header

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

    recent: dict[str, tuple[NavLocator, int]]
    "Most recent NavPos and 'timestamp' by context (commit oid/UNSTAGED/UNTRACKED/STAGED)."

    def __init__(self):
        self.history = []
        self.recent = {}
        self.current = 0
        self.locked = False
        self.counter = 0

    def lock(self):
        """All push calls are ignored while the history is locked."""
        self.locked = True

    def unlock(self):
        self.locked = False

    def push(self, pos: NavLocator):
        if self.locked:
            return

        if not pos:
            log.info("nav", "ignoring:", pos)
            return

        if len(self.history) > 0 and self.history[self.current] == pos:
            log.info("nav", "discarding:", pos)
            return

        self.counter += 1

        self.recent[pos.contextKey] = (pos, self.counter)
        self.recent[pos.fileKey] = (pos, self.counter)

        if self.current < len(self.history) - 1:
            self.trim()

        log.info("nav", F"pushing #{self.counter}:", pos)
        self.history.append(pos)
        self.current = len(self.history) - 1

    def trim(self):
        log.info("nav", F"trimming: {self.current}")
        self.history = self.history[: self.current + 1]
        assert self.isAtTopOfStack

    def bump(self, pos: NavLocator):
        log.info("nav", "bump", pos)

        self.counter += 1

        self.recent[pos.contextKey] = (pos, self.counter)
        self.recent[pos.fileKey] = (pos, self.counter)
    
    @property
    def isAtTopOfStack(self):
        return self.current == len(self.history) - 1

    @property
    def isAtBottomOfStack(self):
        return self.current == 0

    def recallCommit(self, oid: Oid):
        """ Recalls the most recent NavLocator in a commit context. """
        recent = self.recent.get(oid.hex, (None, -1))
        return recent[0]

    def recallWorkdir(self):
        """ Recalls the most recent NavLocator in a workdir context. """
        contextKeys = [NavContext.UNTRACKED.name, NavContext.UNSTAGED.name, NavContext.STAGED.name]
        recents = (self.recent.get(c, (None, -1)) for c in contextKeys)
        return max(recents, key=lambda x: x[1])[0]

    def recallFileInSameContext(self, otherLocator: NavLocator) -> NavLocator:
        pos = self.recent.get(otherLocator.fileKey, (None, -1))
        return pos[0]

    def navigateBack(self):
        if self.current > 0:
            self.current -= 1
            log.info("nav", "back to", self.current, self.history[self.current])
            return self.history[self.current]
        else:
            return None

    def navigateForward(self):
        if self.current < len(self.history) - 1:
            self.current += 1
            log.info("nav", "fwd to", self.current, self.history[self.current])
            return self.history[self.current]
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
