from dataclasses import dataclass
from gitfourchette import log


@dataclass(frozen=True)
class NavPos:
    context: str = ""  # UNSTAGED, UNTRACKED, STAGED or a commit hex oid
    file: str = ""
    diffScroll: int = 0
    diffCursor: int = 0

    def __bool__(self):
        # A position is considered empty iff it has an empty context.
        # The file may be empty with a valid context.
        return bool(self.context)
    
    def __repr__(self) -> str:
        return F"NavPos({self.context[:10]} {self.file} {self.diffScroll} {self.diffCursor})"

    def isWorkdir(self):
        return self.context in ["UNSTAGED", "UNTRACKED", "STAGED"]

    @property
    def fileKey(self):
        """ For NavHistory.recallFileInContext(). """
        return f"{self.context}:{self.file}"


class NavHistory:
    """
    History of the files that the user has viewed in a repository's commit log and workdir.
    """

    history: list[NavPos]
    "Stack of position snapshots."

    current: int
    "Current position in the history stack. Hitting next/forward moves this index."

    recent: dict[str, tuple[NavPos, int]]
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

    def push(self, pos: NavPos):
        if self.locked:
            return

        if not pos:
            log.info("nav", "ignoring:", pos)
            return

        if len(self.history) > 0 and self.history[self.current] == pos:
            log.info("nav", "discarding:", pos)
            return

        self.counter += 1

        self.recent[pos.context] = (pos, self.counter)
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

    def bump(self, pos: NavPos):
        log.info("nav", "bump", pos)

        self.counter += 1

        self.recent[pos.context] = (pos, self.counter)
        self.recent[pos.fileKey] = (pos, self.counter)
    
    @property
    def isAtTopOfStack(self):
        return self.current == len(self.history) - 1

    @property
    def isAtBottomOfStack(self):
        return self.current == 0

    def recall(self, *contexts: str) -> NavPos | None:
        """ Recalls the most recent NavPos matching any of the given contexts. """
        recents = (self.recent.get(c, (None, -1)) for c in contexts)
        return max(recents, key=lambda x: x[1])[0]

    def recallFileInContext(self, context: str, file: str) -> NavPos:
        pos = self.recent.get(F"{context}:{file}", (None, -1))
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
            s += f"{h.context[:7]} {h.file:32} {h.diffScroll} {h.diffCursor}"
            i -= 1
        return s
