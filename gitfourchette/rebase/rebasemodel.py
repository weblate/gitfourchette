# -----------------------------------------------------------------------------
# Copyright (C) 2026 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

from __future__ import annotations  # TODO: Remove once we can drop support for Python <= 3.13

import base64
import dataclasses
import enum
import re
from typing import Any, ClassVar

from gitfourchette import colors
from gitfourchette.porcelain import Oid, RefPrefix
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

    def isEditable(self):
        return self == "reword" or self == "squash"


SupportedRebaseOps = {
    RebaseOp.Pick,
    RebaseOp.Reword,
    RebaseOp.Edit,
    # RebaseOp.Squash,  # TODO - need message edit support
    RebaseOp.Fixup,
    RebaseOp.Drop,
}


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


_PayloadMagicPrefix = "GITFOURCHETTE_REBASE_PAYLOAD="


@dataclasses.dataclass
class RebaseLine:
    EmptyCommitSuffix: ClassVar = " # empty"

    op: RebaseOp
    hexHash: str
    originalComment: str = ""
    payload: str = ""

    verifiedEmpty: bool = dataclasses.field(default=False, compare=False)
    """ True if we've verified that the commit has no changes w/r/t its first
    parent. """

    def displayMessage(self, unmodified: bool = False) -> str:
        if not unmodified and self.op.isEditable() and self.payload:
            return self.payload
        elif self.verifiedEmpty:
            return self.originalComment.removesuffix(RebaseLine.EmptyCommitSuffix)
        else:
            return self.originalComment

    def copy(self) -> RebaseLine:
        return dataclasses.replace(self)

    def __str__(self) -> str:
        # Note that git strips comment-only lines from .git/rebase-merge/git-rebase-todo,
        # so our payload must fit on the same line as the opcode.
        if self.op.isEditable() and self.payload:
            payloadBase64 = base64.b64encode(self.payload.encode("utf-8"))
            comment = "#" + _PayloadMagicPrefix + payloadBase64.decode("ascii")
        else:
            comment = "# " + self.originalComment

        return f"{self.op} {self.hexHash} {comment}"


TRebaseSequence = list[RebaseLine]


@dataclasses.dataclass
class RebasePlan:
    sequence: TRebaseSequence
    headName: str
    origHead: Oid
    onto: Oid

    def serializeSequence(self) -> str:
        return "\n".join(str(line) for line in self.sequence)

    @property
    def headShorthand(self) -> str:
        return RefPrefix.split(self.headName)[1]


class RebaseLineWrapper(QListWidgetItem):
    def __init__(self, item: RebaseLine):
        super().__init__()
        self.item = item.copy()
        self.updateFlags()

    def data(self, role: int):
        if role == Qt.ItemDataRole.DisplayRole:
            return str(self.item)
        elif role == Qt.ItemDataRole.UserRole:
            return self.item
        elif role == Qt.ItemDataRole.ToolTipRole:
            return self.item.hexHash
        elif role == Qt.ItemDataRole.EditRole:
            # Message filling in QLineEdit
            return self.item.displayMessage()
        return super().data(role)

    def updateFlags(self):
        flags = self.flags()
        if self.item.op.isEditable():
            flags |= Qt.ItemFlag.ItemIsEditable
        else:
            flags &= ~Qt.ItemFlag.ItemIsEditable
        self.setFlags(flags)

    def setData(self, role: int, value: Any):
        # Called when the line edit has finished editing text.
        # Only allowed on Reword and Squash.
        assert role == Qt.ItemDataRole.EditRole
        assert self.item.op.isEditable()
        assert isinstance(value, str)

        # Don't override if identical to original comment
        if value == self.item.displayMessage(unmodified=True):
            value = ""

        self.item.payload = value


def parseRebaseTodo(text: str) -> TRebaseSequence:
    CommentMarker = "#"
    sequence: TRebaseSequence = []
    for line in text.splitlines():
        line = line.strip()

        if not line or line.startswith(CommentMarker):
            continue

        if _todoNoopPattern.match(line):
            continue

        match = _todoLinePattern.match(line)
        assert match is not None, f"unsupported todo line: {line}"
        commandName, hexHash, comment = match.groups()

        if comment.startswith(_PayloadMagicPrefix):
            payloadBase64 = comment.removeprefix(_PayloadMagicPrefix)
            editedMessage = base64.b64decode(payloadBase64).decode("utf-8")
        else:
            editedMessage = ""

        item = RebaseLine(RebaseOp(commandName), hexHash, comment, editedMessage)
        sequence.append(item)
    return sequence


_opsRegex = "|".join(RebaseOp)
_todoNoopPattern = re.compile(r"^noop\b")
_todoLinePattern = re.compile(rf"^({_opsRegex})\s+([0-9a-f]+)(?:\s*#\s*|\s+)(.+)$")
#                                                             ^^^^^^^^^
# Note: At some point between git 2.43 and 2.54, git rebase started adding
# comment marks in todo lines. We're treating those as optional for now.
