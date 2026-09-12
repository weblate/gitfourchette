# -----------------------------------------------------------------------------
# Copyright (C) 2026 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

from __future__ import annotations  # TODO: Remove once we can drop support for Python <= 3.13

from typing import Any

from gitfourchette import settings
from gitfourchette.qt import *
from gitfourchette.rebase.rebasemodel import TRebaseSequence, RebaseLine
from gitfourchette.toolbox import QModelIndex_default


class RebaseSequenceModel(QAbstractListModel):
    RebaseLineRole = Qt.ItemDataRole.UserRole

    sequence: TRebaseSequence

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.sequence = []

    def setSequence(self, sequence: TRebaseSequence):
        self.sequence = sequence

    def flipRow(self, i: int) -> int:
        if settings.prefs.rebaseBottomUp:
            i = len(self.sequence) - 1 - i
        return i

    def rebaseLineAtRow(self, row: int) -> RebaseLine:
        i = self.flipRow(row)
        return self.sequence[i]

    def supportedDropActions(self):
        return Qt.DropAction.MoveAction

    def moveRows(
        self,
        sourceParent: QModelIndex,
        sourceRow: int,
        count: int,
        destinationParent: QModelIndex,
        destinationChild: int,
    ) -> bool:
        assert not sourceParent.isValid(), "source must be root index"
        assert sourceParent == destinationParent, "must move to root index"
        assert count >= 1

        beginMoveRowsOK = self.beginMoveRows(
            sourceParent,
            sourceRow,
            sourceRow + count - 1,
            destinationParent,
            destinationChild)

        # PyQt6 6.11 always returns beginMoveRowsOK==True, but PyQt6 6.6.1 might not.
        if not beginMoveRowsOK:
            return False

        insertAt = destinationChild
        if insertAt > sourceRow:
            insertAt -= count

        s1 = self.flipRow(sourceRow)
        s2 = self.flipRow(sourceRow + count - 1)
        s1, s2 = min(s1, s2), max(s1, s2)
        insertAt = self.flipRow(insertAt)

        moved = self.sequence[s1 : s2+1]
        del self.sequence[s1 : s2+1]
        self.sequence[insertAt : insertAt] = moved

        self.endMoveRows()
        return True

    def rowCount(self, parent: QModelIndex = QModelIndex_default) -> int:
        assert not parent.isValid(), "expecting root index only"
        return len(self.sequence)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        assert index.isValid(), "expecting non-root index"

        try:
            item = self.rebaseLineAtRow(index.row())
        except IndexError:
            return None

        if role == Qt.ItemDataRole.DisplayRole:
            return str(item)

        if role == Qt.ItemDataRole.EditRole:
            # Message filling in QLineEdit
            return item.displayMessage()

        if role == RebaseSequenceModel.RebaseLineRole:
            return item

        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        flags = super().flags(index)
        flags |= Qt.ItemFlag.ItemNeverHasChildren

        # Allow dragging inbetween items
        if not index.isValid():
            return flags | Qt.ItemFlag.ItemIsDropEnabled

        item = self.rebaseLineAtRow(index.row())
        flags |= (Qt.ItemFlag.ItemIsEnabled
                  | Qt.ItemFlag.ItemIsSelectable
                  | Qt.ItemFlag.ItemIsDragEnabled)
        if item.op.isEditable():
            flags |= Qt.ItemFlag.ItemIsEditable
        return flags

    def setData(self, index: QModelIndex, value: Any, role = ...):
        item = self.rebaseLineAtRow(index.row())

        # Called when the line edit has finished editing text.
        # Only allowed on Reword and Squash.
        assert role == Qt.ItemDataRole.EditRole, f"{role!r}"
        assert item.op.isEditable()
        assert isinstance(value, str)

        # Don't override if identical to original comment
        if value == item.displayMessage(unmodified=True):
            value = ""

        item.payload = value

        self.emitUserDataChanged([index])
        return True

    def emitUserDataChanged(self, indexes: list[QModelIndex]):
        top = min(indexes, key=QModelIndex.row)
        bottom = max(indexes, key=QModelIndex.row)
        self.dataChanged.emit(top, bottom, [RebaseSequenceModel.RebaseLineRole])
