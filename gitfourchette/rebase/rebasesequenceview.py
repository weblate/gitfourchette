# -----------------------------------------------------------------------------
# Copyright (C) 2026 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

from gitfourchette.localization import *
from gitfourchette.qt import *
from gitfourchette.rebase.rebasemodel import RebaseLine, RebaseOp, RebaseOpLetters, SupportedRebaseOps, TRebaseSequence
from gitfourchette.rebase.rebasesequencedelegate import RebaseSequenceDelegate
from gitfourchette.rebase.rebasesequencemodel import RebaseSequenceModel
from gitfourchette.rebase.rebasesequencedropindicator import RebaseSequenceDropIndicator
from gitfourchette.toolbox.gitutils import *
from gitfourchette.toolbox.qtutils import itemViewBestIndexOnSelectionChanged
from gitfourchette.toolbox.textutils import *


_RebaseOpsByHotkey = {letter: op for op, letter in RebaseOpLetters.items()}


class RebaseSequenceView(QListView):
    opShortcut = Signal(RebaseOp)
    commitSelected = Signal(Oid)

    sequenceModel: RebaseSequenceModel

    def __init__(self, parent=None):
        super().__init__(parent)

        delegate = RebaseSequenceDelegate(self)
        self.setItemDelegate(delegate)

        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setUniformItemSizes(True)
        self.setEditTriggers(QListView.EditTrigger.DoubleClicked | QListView.EditTrigger.EditKeyPressed)

        self.dropIndicator = RebaseSequenceDropIndicator(self.viewport())
        self.dropIndicator.setFixedHeight(32)
        self.dropIndicator.hide()
        self.setDropIndicatorShown(False)  # remove Qt's native indicator

        self.sequenceModel = RebaseSequenceModel(self)
        self.setModel(self.sequenceModel)

    def selectionChanged(self, selected: QItemSelection, deselected: QItemSelection):
        super().selectionChanged(selected, deselected)

        current = itemViewBestIndexOnSelectionChanged(self, selected)
        if current.isValid():
            rebaseLine = current.data(RebaseSequenceModel.RebaseLineRole)
            self.commitSelected.emit(rebaseLine.oid)

    def effectiveSequence(self) -> TRebaseSequence:
        return [line for line in self.sequenceModel.sequence if not line.op.isFake()]

    def selectedRebaseLines(self) -> list[RebaseLine]:
        lines = [index.data(RebaseSequenceModel.RebaseLineRole) for index in self.selectedIndexes()]
        assert all(isinstance(i, RebaseLine) for i in lines)
        return lines

    def keyboardSearch(self, search: str):
        pass

    def keyPressEvent(self, event: QKeyEvent):
        op: RebaseOp | None = None
        text = event.text().lower()

        if text in _RebaseOpsByHotkey:
            op = _RebaseOpsByHotkey[text]
        elif event.key() == Qt.Key.Key_F2:
            op = RebaseOp.Reword

        if op in SupportedRebaseOps:
            self.opShortcut.emit(op)
        else:
            super().keyPressEvent(event)

    def dragMoveEvent(self, event: QDragMoveEvent):
        super().dragMoveEvent(event)
        self.dropIndicator.syncPositionOnDrag(event, self)

    def dragLeaveEvent(self, event: QDragLeaveEvent):
        super().dragLeaveEvent(event)
        self.dropIndicator.hide()

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

        drag = self.makeQDrag()

        try:
            # Note: this returns immediately in offscreen mode!
            drag.exec(supportedActions)
        finally:
            delegate.ignoreMouseOverState = False
            self.dropIndicator.hide()
            self.viewport().update()

    def makeQDrag(self) -> QDrag:
        # Set custom floating drag indicator
        selectedRebaseLines = self.selectedRebaseLines()
        mimeData = self.model().mimeData(self.selectedIndexes())

        # Font
        font = QFont(self.font())
        font.setBold(True)
        fontMetrics = QFontMetricsF(font)

        # Text
        if len(selectedRebaseLines) == 1:
            text = _("Move {0}", tquo(shortHash(selectedRebaseLines[0].hexHash)))
        else:
            text = _n("Move {n} commit", "Move {n} commits", n=len(selectedRebaseLines))

        # Metrics
        height = int(fontMetrics.lineSpacing() * 1.5)
        lMargin = int(height * 1.66)
        rMargin = int(height * .66)
        width = int(fontMetrics.horizontalAdvance(text) + lMargin + rMargin)
        pt = 2  # Pen Thickness
        rect = QRect(0, 0, width, height)

        # Colors
        fgColor = Qt.GlobalColor.white
        bgColor = QApplication.palette().accent().color()

        drag = QDrag(self)
        drag.setMimeData(mimeData)

        # Must render pixmap at DPR, otherwise looks pixelated @2x
        dpr = self.devicePixelRatio()
        pixmap = QPixmap(rect.size() * dpr)
        pixmap.setDevicePixelRatio(dpr)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(bgColor)
        painter.setPen(QPen(fgColor, pt, Qt.PenStyle.DotLine))
        painter.drawRoundedRect(QRectF(rect).adjusted(pt/2, pt/2, -pt/2, -pt/2), height/2, height/2)
        painter.setFont(font)
        painter.drawText(rect.adjusted(lMargin, 0, 0, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)
        painter.end()

        drag.setPixmap(pixmap)
        drag.setHotSpot(QPoint(lMargin//2, height // 2))

        return drag
