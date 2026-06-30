# -----------------------------------------------------------------------------
# Copyright (C) 2026 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

import math

from gitfourchette.qt import *
from gitfourchette.rebase.rebasemodel import RebaseLine, RebaseOp, RebaseOpColors
from gitfourchette.toolbox import shortHash, mixColors

_ItemRole = Qt.ItemDataRole.UserRole
_FallbackColor = QColor(Qt.GlobalColor.magenta)
_ColumnPadding = 8


class RebaseSequenceDelegate(QStyledItemDelegate):
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        widget = option.widget
        isActive = bool(option.state & QStyle.StateFlag.State_Active)
        isSelected = bool(option.state & QStyle.StateFlag.State_Selected)
        colorGroup = QPalette.ColorGroup.Active if isActive else QPalette.ColorGroup.Inactive

        # Gather data from model
        item: RebaseLine = index.data(_ItemRole)

        # Begin painting
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        fontMetrics = painter.fontMetrics()
        rect = QRect(option.rect)
        rect.adjust(2, 0, -2, 0)

        # Draw default background
        widget.style().drawControl(QStyle.ControlElement.CE_ItemViewItem, option, painter, widget)

        # Draw pill
        blendAbove, blendBelow = self.pillBlending(index)
        self.drawPill(painter, rect, item.op, blendAbove, blendBelow)
        rect.adjust(_ColumnPadding, 0, 0, 0)

        # Draw hash
        hcw = max(option.fontMetrics.horizontalAdvance(c) for c in "0123456789abcdef")
        charRect = QRect(rect.left(), rect.top(), hcw, rect.height())
        colorRole = QPalette.ColorRole.HighlightedText if isSelected else QPalette.ColorRole.PlaceholderText
        textColor = option.palette.color(colorGroup, colorRole)
        painter.setPen(textColor)
        for hashChar in shortHash(item.hexHash):
            painter.drawText(charRect, Qt.AlignmentFlag.AlignCenter, hashChar)
            charRect.translate(hcw, 0)
        rect.setLeft(charRect.left() + _ColumnPadding)

        # Draw message
        text = fontMetrics.elidedText(item.comment, option.textElideMode, rect.width())
        colorRole = QPalette.ColorRole.HighlightedText if isSelected else QPalette.ColorRole.WindowText
        textColor = option.palette.color(colorGroup, colorRole)
        painter.setPen(textColor)
        painter.drawText(rect, option.displayAlignment, text)

        # Finish painting
        painter.restore()

    @staticmethod
    def drawPill(
            painter: QPainter,
            rect: QRect,
            op: RebaseOp,
            opAbove: RebaseOp | None,
            opBelow: RebaseOp | None,
    ):
        painter.save()

        font = QFont(painter.font())
        font.setBold(True)
        painter.setFont(font)

        vMargin = max(0, math.ceil((rect.height() - 16) / 4))  # Vertical margin
        rrRadius = rect.height() // 2
        width = painter.fontMetrics().horizontalAdvance("ooooo") + 2 * rrRadius

        textRect = QRectF(rect)
        textRect.adjust(0, vMargin, 0, -vMargin)
        textRect.setWidth(width)

        # Snap pill to pixel grid;
        # Extend pill beyond vertical bounds if connecting above and/or below
        pillRect = textRect.adjusted(
            .5,
            .5 - (vMargin+rrRadius if opAbove else 0),
            .5,
            -.5 + (vMargin+rrRadius if opBelow else 0))
        pillPath = QPainterPath()
        pillPath.addRoundedRect(pillRect, rrRadius, rrRadius)

        # Gradient
        colorCenter = RebaseOpColors.get(op, _FallbackColor)
        colorAbove = RebaseOpColors.get(opAbove or op, _FallbackColor)
        colorBelow = RebaseOpColors.get(opBelow or op, _FallbackColor)
        colorAbove = mixColors(colorCenter, colorAbove)
        colorBelow = mixColors(colorCenter, colorBelow)
        gradientSpan = .2
        gradient = QLinearGradient(0, rect.top(), 0, rect.bottom() + 1)
        gradient.setColorAt(0, colorAbove)
        gradient.setColorAt(gradientSpan, colorCenter)
        gradient.setColorAt(1-gradientSpan, colorCenter)
        gradient.setColorAt(1, colorBelow)

        # Op name
        # Add question mark if attempting to fixup nothing
        opText = str(op)
        if op == RebaseOp.Fixup and not opAbove:
            opText = f"¿{opText}?"

        # Paint
        painter.setClipRect(rect)  # confine drawing to row
        painter.setPen(Qt.GlobalColor.white)
        painter.fillPath(pillPath, gradient)
        painter.drawPath(pillPath)
        painter.drawText(textRect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter, opText)
        painter.restore()

        rect.setLeft(round(textRect.right()))

    @staticmethod
    def pillBlending(index: QModelIndex) -> tuple[RebaseOp | None, RebaseOp | None]:
        connectAbove = False
        connectBelow = False
        opAbove: RebaseOp | None = None
        opBelow: RebaseOp | None = None

        model: QAbstractItemModel = index.model()
        startOp: RebaseOp = index.data(_ItemRole).op
        startRow = index.row()
        startCol = index.column()

        for row in range(startRow + 1, model.rowCount()):
            index = model.index(row, startCol)
            assert index.isValid()
            op: RebaseOp = index.data(_ItemRole).op
            if op == RebaseOp.Drop:
                continue
            if op == RebaseOp.Fixup:
                connectBelow = True
            break

        if startOp == RebaseOp.Fixup:
            connectAbove = startRow != 0
        elif startOp == RebaseOp.Drop:
            connectAbove = connectBelow

        if connectAbove:
            above = model.index(startRow - 1, 0)
            if above.isValid():
                opAbove = above.data(_ItemRole).op

        if connectBelow:
            below = model.index(startRow + 1, 0)
            assert below.isValid()
            opBelow = below.data(_ItemRole).op

        return opAbove, opBelow
