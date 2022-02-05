from copy import copy
from dataclasses import dataclass


@dataclass
class NavPos:
    context: str = ""  # UNSTAGED, UNTRACKED, STAGED or a commit hex oid
    file: str = ""
    diffScroll: int = 0
    diffCursor: int = 0


class NavHistory:
    history: list[NavPos]
    recent: dict[str, NavPos]

    def __init__(self):
        self.history = []
        self.recent = {}

    def push(self, pos: NavPos):
        if len(self.history) == 0 or self.history[-1] != pos:
            print("NavHistory: pushing:", pos)
            pos = copy(pos)
            self.recent[pos.context] = pos
            self.recent[F"{pos.context}:{pos.file}"] = pos
            self.history.append(pos)

    def findContext(self, context):
        pos = self.recent.get(context, None)
        return copy(pos) if pos else None

    def findFileInContext(self, context, file):
        pos = self.recent.get(F"{context}:{file}", None)
        return copy(pos) if pos else None
