# -----------------------------------------------------------------------------
# Copyright (C) 2026 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

import math

from gitfourchette import colors
from gitfourchette.qt import *
from gitfourchette.rebase.rebasemodel import RebaseOp, RebaseLine
from gitfourchette.toolbox import shortHash

RebaseOpColors = {
    "pick"      : colors.gray,
    "reword"    : colors.purple,
    "edit"      : colors.yellow,
    "fixup"     : colors.teal,
    "drop"      : colors.red,
}


class RebaseSequenceDelegate(QStyledItemDelegate):
    @staticmethod
    def drawOpPill(painter: QPainter, rect: QRect, op: RebaseOp):
        painter.save()

        font = QFont(painter.font())
        font.setBold(True)
        painter.setFont(font)

        vMargin = max(0, math.ceil((rect.height() - 16) / 4))  # Vertical margin
        rrRadius = rect.height() // 2
        width = painter.fontMetrics().horizontalAdvance("ooooo") + 2 * rrRadius

        frameRect = QRectF(rect)
        frameRect.adjust(0, vMargin, 0, -vMargin)
        frameRect.setWidth(width)

        framePath = QPainterPath()
        framePath.addRoundedRect(frameRect.adjusted(.5, .5, .5, -.5),  # Snap to pixel grid
                                 rrRadius, rrRadius)

        painter.setPen(Qt.GlobalColor.white)
        painter.fillPath(framePath, RebaseOpColors.get(op, colors.gray))
        painter.drawPath(framePath)
        painter.drawText(frameRect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter, op)

        painter.restore()
        rect.setLeft(round(frameRect.right()) + 6)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        widget = option.widget
        isActive = bool(option.state & QStyle.StateFlag.State_Active)
        isSelected = bool(option.state & QStyle.StateFlag.State_Selected)
        colorGroup = QPalette.ColorGroup.Active if isActive else QPalette.ColorGroup.Inactive

        # Gather data from model
        item: RebaseLine = index.data(Qt.ItemDataRole.UserRole)

        # Begin painting
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        fontMetrics = painter.fontMetrics()
        rect = QRect(option.rect)
        rect.adjust(2, 0, -2, 0)

        # Draw default background
        widget.style().drawControl(QStyle.ControlElement.CE_ItemViewItem, option, painter, widget)

        # Draw pill
        self.drawOpPill(painter, rect, item.op)

        # Draw hash
        hcw = max(option.fontMetrics.horizontalAdvance(c) for c in "0123456789abcdef")
        charRect = QRect(rect.left(), rect.top(), hcw, rect.height())
        colorRole = QPalette.ColorRole.HighlightedText if isSelected else QPalette.ColorRole.PlaceholderText
        textColor = option.palette.color(colorGroup, colorRole)
        painter.setPen(textColor)
        for hashChar in shortHash(item.hexHash):
            painter.drawText(charRect, Qt.AlignmentFlag.AlignCenter, hashChar)
            charRect.translate(hcw, 0)
        rect.setLeft(charRect.left() + 6)

        # Draw message
        text = fontMetrics.elidedText(item.comment, option.textElideMode, rect.width())
        colorRole = QPalette.ColorRole.HighlightedText if isSelected else QPalette.ColorRole.WindowText
        textColor = option.palette.color(colorGroup, colorRole)
        painter.setPen(textColor)
        painter.drawText(rect, option.displayAlignment, text)

        # Finish painting
        painter.restore()


