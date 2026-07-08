# -----------------------------------------------------------------------------
# Copyright (C) 2026 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

from gitfourchette.qt import *
from gitfourchette.rebase.rebasemodel import RebaseLine
from gitfourchette.rebase.rebasesequencedelegate import RebaseSequenceDelegate
from gitfourchette.rebase.rebasesequencestyle import RebaseSequenceStyle


class RebaseSequenceView(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        delegate = RebaseSequenceDelegate(self)
        self.setItemDelegate(delegate)

        styleProxy = RebaseSequenceStyle()  # provides nicer PE_IndicatorItemViewItemDrop
        self.setStyle(styleProxy)

        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setUniformItemSizes(True)
        self.setEditTriggers(QListView.EditTrigger.DoubleClicked | QListView.EditTrigger.EditKeyPressed)

    def allRebaseLines(self) -> list[RebaseLine]:
        lines = [self.item(row).item for row in range(self.count())]  # type: ignore[attr-defined]
        assert all(isinstance(i, RebaseLine) for i in lines)
        return lines

    def selectedRebaseLines(self) -> list[RebaseLine]:
        lines = [wrapper.item for wrapper in self.selectedItems()]  # type: ignore[attr-defined]
        assert all(isinstance(i, RebaseLine) for i in lines)
        return lines

    def supportedDropActions(self) -> Qt.DropAction:
        # Override default MoveAction|CopyAction to prevent copying items by
        # holding Ctrl while dragging.
        return Qt.DropAction.MoveAction

    def startDrag(self, supportedActions: Qt.DropAction):
        """
        The Breeze style draws items with a hover rectangle as the mouse cursor
        sweeps over them while dragging another item. This looks misleading, so
        override this behavior.
        """
        delegate = self.itemDelegate()
        assert isinstance(delegate, RebaseSequenceDelegate)
        delegate.ignoreMouseOverState = True
        self.viewport().update()
        try:
            super().startDrag(supportedActions)
        finally:
            delegate.ignoreMouseOverState = False
            self.viewport().update()
