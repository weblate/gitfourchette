# -----------------------------------------------------------------------------
# Copyright (C) 2026 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

import dataclasses
import enum
import re

from gitfourchette import colors
from gitfourchette.qt import *


class RebaseOp(enum.StrEnum):
    Pick        = "pick"
    Reword      = "reword"
    Edit        = "edit"
    Squash      = "squash"
    Fixup       = "fixup"
    Exec        = "exec"
    Break       = "break"
    Drop        = "drop"
    Label       = "label"
    Reset       = "reset"
    Merge       = "merge"
    UpdateRef   = "update-ref"


RebaseOpLetters: dict[RebaseOp, str] = {
    RebaseOp.Pick       : "p",
    RebaseOp.Reword     : "r",
    RebaseOp.Edit       : "e",
    RebaseOp.Squash     : "s",
    RebaseOp.Fixup      : "f",
    RebaseOp.Exec       : "x",
    RebaseOp.Break      : "b",
    RebaseOp.Drop       : "d",
    RebaseOp.Label      : "l",
    RebaseOp.Reset      : "t",
    RebaseOp.Merge      : "m",
    RebaseOp.UpdateRef  : "u",
}


RebaseOpColors: dict[RebaseOp, QColor] = {
    RebaseOp.Pick      : colors.olive,
    RebaseOp.Edit      : colors.yellow,
    RebaseOp.Reword    : QColor(0xFFD18DE1),
    RebaseOp.Squash    : colors.blue,
    RebaseOp.Fixup     : colors.teal,
    RebaseOp.Drop      : colors.red,
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
