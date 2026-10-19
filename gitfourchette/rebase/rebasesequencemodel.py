# -----------------------------------------------------------------------------
# Copyright (C) 2026 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

from __future__ import annotations  # TODO: Remove once we can drop support for Python <= 3.13

from typing import Any

from gitfourchette import settings
from gitfourchette.qt import *
from gitfourchette.rebase.rebasemodel import TRebaseSequence, RebaseLine, RebaseOp
from gitfourchette.toolbox import QModelIndex_default


class RebaseSequenceModel(QAbstractListModel):
    RebaseLineRole = Qt.ItemDataRole.UserRole
    RebaseDanglingRole = Qt.ItemDataRole.UserRole + 1

    sequence: TRebaseSequence

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.sequence = []
        self.danglingHash = ""

    def replaceSequence(self, sequence: TRebaseSequence):
        if sequence == self.sequence:
            # Ignore spam calls from QUndoStack.push (via RebaseUndoCommand.redo)
            return

        sequenceCopy = [line.copy() for line in sequence]

        self.beginResetModel()

        self.sequence = sequenceCopy
        self.refreshDanglingHash()

        self.endResetModel()

    def refreshDanglingHash(self):
        self.danglingHash = ""
        for line in self.sequence:
            if line.op in [RebaseOp.Pick, RebaseOp.Reword, RebaseOp.Edit]:
                break
            if line.op in [RebaseOp.Fixup, RebaseOp.Squash]:
                self.danglingHash = line.hexHash
                break

    def flipRow(self, i: int) -> int:
        if settings.prefs.rebaseBottomUp:
            i = len(self.sequence) - 1 - i
        return i

    def canInsertAtRow(self, row: int) -> bool:
        flippedRow = self.flipRow(row)
        return flippedRow >= 0

    def rebaseLineAtRow(self, row: int) -> RebaseLine:
        i = self.flipRow(row)
        return self.sequence[i]

    def supportedDropActions(self):
        return Qt.DropAction.MoveAction

    def dropMimeData(self, data, action, row, column, parent) -> bool:
        # Prevent Qt from calling setData when dropping rows
        return False

    def canDropMimeData(self, data: QMimeData, action: Qt.DropAction, row: int, column: int, parent: QModelIndex) -> bool:
        # Reimplemented with additional row check. If the row is incorrect, the
        # 'denied' mouse pointer appears and the drop indicator vanishes.
        superCanDrop = super().canDropMimeData(data, action, row, column, parent)
        return superCanDrop and self.canInsertAtRow(row)

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

        # Prevent dragging beyond start row
        if not self.canInsertAtRow(destinationChild):
            return False

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

        if role == RebaseSequenceModel.RebaseDanglingRole:
            return item.hexHash == self.danglingHash

        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        flags = super().flags(index)
        flags |= Qt.ItemFlag.ItemNeverHasChildren

        # Allow dragging inbetween items
        if not index.isValid():
            return flags | Qt.ItemFlag.ItemIsDropEnabled

        item = self.rebaseLineAtRow(index.row())

        if item.op == RebaseOp.FakeStart:
            return Qt.ItemFlag.NoItemFlags

        flags |= (Qt.ItemFlag.ItemIsEnabled
                  | Qt.ItemFlag.ItemIsSelectable
                  | Qt.ItemFlag.ItemIsDragEnabled)
        if item.op.isEditable():
            flags |= Qt.ItemFlag.ItemIsEditable
        return flags

    def setData(self, index: QModelIndex, value: Any, role: int = Qt.ItemDataRole.EditRole):
        """
        Called when the line edit has finished editing commit message text.
        Only allowed on Reword and Squash.
        """

        item = self.rebaseLineAtRow(index.row())

        assert role == Qt.ItemDataRole.EditRole, f"{index.row()} {role!r} {value!r}"
        assert item.op.isEditable()
        assert isinstance(value, str)

        # Don't override if identical to original comment
        if value == item.displayMessage(unmodified=True):
            value = ""

        # Git will strip whitespace in commit messages
        value = value.strip()

        item.payload = value

        self.emitUserDataChanged([index])
        return True

    def emitUserDataChanged(self, indexes: list[QModelIndex]):
        top = min(indexes, key=QModelIndex.row)
        bottom = max(indexes, key=QModelIndex.row)
        self.dataChanged.emit(top, bottom, [RebaseSequenceModel.RebaseLineRole])


class RebaseUndoCommand(QUndoCommand):
    def __init__(
            self,
            undoSequence: TRebaseSequence,
            redoSequence: TRebaseSequence,
            model: RebaseSequenceModel,
    ):
        super().__init__()
        self.undoSequence = [line.copy() for line in undoSequence]
        self.redoSequence = [line.copy() for line in redoSequence]
        self.sequenceModel = model

    def undo(self):
        self.sequenceModel.replaceSequence(self.undoSequence)

    def redo(self):
        self.sequenceModel.replaceSequence(self.redoSequence)
