# -----------------------------------------------------------------------------
# Copyright (C) 2026 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

import dataclasses
import enum
import re

from gitfourchette.qt import *


# Commented entries are not supported by GitFourchette
class RebaseOp(enum.StrEnum):
    Pick        = "pick"
    # Reword      = "reword"  # TODO - need message edit support
    Edit        = "edit"
    # Squash      = "squash"  # TODO - need message edit support
    Fixup       = "fixup"
    # Exec        = "exec"
    # Break       = "break"
    Drop        = "drop"
    # Label       = "label"
    # Reset       = "reset"
    # Merge       = "merge"
    # UpdateRef   = "update-ref"


RebaseOpLetters = {
    "pick"      : "p",
    "reword"    : "r",
    "edit"      : "e",
    "squash"    : "s",
    "fixup"     : "f",
    "exec"      : "x",
    "break"     : "b",
    "drop"      : "d",
    "label"     : "l",
    "reset"     : "t",
    "merge"     : "m",
    "update-ref": "u",
}


@dataclasses.dataclass
class RebaseLine:
    op: RebaseOp
    hexHash: str
    comment: str = ""

    def __str__(self) -> str:
        # TODO: we could pass special info to the message editor via the comment.
        # Note that git strips comment-only lines from .git/rebase-merge/git-rebase-todo
        # (or why not just dump our data in .git/rebase-merge/gitfourchetterebase.json?)
        return f"{self.op} {self.hexHash} # {self.comment}"

TRebaseSequence = list[RebaseLine]


class RebaseLineWrapper(QListWidgetItem):
    def __init__(self, item: RebaseLine):
        super().__init__()
        self.item = item

    def data(self, role: int):
        if role == Qt.ItemDataRole.DisplayRole:
            return str(self.item)
        elif role == Qt.ItemDataRole.UserRole:
            return self.item
        elif role == Qt.ItemDataRole.ToolTipRole:
            return self.item.hexHash
        return super().data(role)


def parseRebaseTodo(text: str) -> TRebaseSequence:
    CommentMarker = "#"
    sequence: TRebaseSequence = []
    for line in text.splitlines():
        line = line.strip()
        # TODO: handle noop?
        if not line or line.startswith(CommentMarker):
            continue
        match = _todoLinePattern.match(line)
        assert match is not None, f"unsupported todo line: {line}"
        commandName, hexHash, comment = match.groups()
        item = RebaseLine(RebaseOp(commandName), hexHash, comment)
        sequence.append(item)
    return sequence


_opsRegex = "|".join(RebaseOp)
_todoLinePattern = re.compile(rf"^({_opsRegex})\s+([0-9a-f]+)(?:\s*#\s*|\s+)(.+)$")
#                                                             ^^^^^^^^^
# Note: At some point between git 2.43 and 2.54, git rebase started adding
# comment marks in todo lines. We're treating those as optional for now.
