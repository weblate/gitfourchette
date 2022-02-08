from copy import copy
from dataclasses import dataclass


@dataclass
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

    def copy(self):
        return copy(self)


class NavHistory:
    history: list[NavPos]
    recent: dict[str, NavPos]
    current: int

    def __init__(self):
        self.history = []
        self.recent = {}
        self.current = 0
        self.locked = False

    def lock(self):
        self.locked = True

    def unlock(self):
        self.locked = False

    def push(self, pos: NavPos):
        if self.locked:
            return

        if not pos:
            print("[nav] ignoring:", pos)
            return

        if len(self.history) == 0 or self.history[self.current] != pos:
            pos = pos.copy()
            self.recent[pos.context] = pos
            self.recent[F"{pos.context}:{pos.file}"] = pos

            if self.current < len(self.history) - 1:
                self.trim()

            print(F"[nav] pushing #{len(self.history)}:", pos)
            self.history.append(pos)
            self.current = len(self.history) - 1
        else:
            print("[nav] discarding:", pos)

    def trim(self):
        print(F"[nav] trimming {self.current}")
        self.history = self.history[: self.current + 1]
        assert self.isAtTopOfStack

    def setRecent(self, pos):
        print("[nav] setRecent", pos)
        pos = copy(pos)
        self.recent[pos.context] = pos
        self.recent[F"{pos.context}:{pos.file}"] = pos
    
    @property
    def isAtTopOfStack(self):
        return self.current == len(self.history) - 1

    @property
    def isAtBottomOfStack(self):
        return self.current == 0

    def findContext(self, context):
        pos = self.recent.get(context, None)
        return copy(pos) if pos else None

    def findFileInContext(self, context, file):
        pos = self.recent.get(F"{context}:{file}", None)
        return copy(pos) if pos else None

    def navigateBack(self):
        if self.current > 0:
            self.current -= 1
            print("[nav] back to", self.current, self.history[self.current])
            return self.history[self.current]
        else:
            return None

    def navigateForward(self):
        if self.current < len(self.history) - 1:
            self.current += 1
            print("[nav] fwd to", self.current, self.history[self.current])
            return self.history[self.current]
        else:
            return None
