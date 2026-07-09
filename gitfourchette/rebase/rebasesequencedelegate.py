# -----------------------------------------------------------------------------
# Copyright (C) 2026 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

import math

from gitfourchette import settings
from gitfourchette.localization import *
from gitfourchette.qt import *
from gitfourchette.rebase.rebasemodel import RebaseLine, RebaseOp, RebaseOpColors
from gitfourchette.toolbox import shortHash, mixColors

_ItemRole = Qt.ItemDataRole.UserRole
_FallbackColor = QColor(Qt.GlobalColor.magenta)
_ColumnPadding = 8


class RebaseSequenceDelegate(QStyledItemDelegate):
    ignoreMouseOverState: bool

    def __init__(self, parent=None):
        super().__init__(parent)
        self.ignoreMouseOverState = False

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        height = settings.prefs.calcRowHeight(option.fontMetrics)
        size = super().sizeHint(option, index)
        size.setHeight(height)
        return size

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        if self.ignoreMouseOverState:
            option.state &= ~QStyle.StateFlag.State_MouseOver

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
        # Note: PySide6 crashes accessing widget.style() if it's a proxy style
        style = QApplication.style() if PYSIDE6 else widget.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, option, painter, widget)

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
        if item.op.isEditable():
            editableFont = QFont(painter.font())
            editableFont.setItalic(True)
            painter.setFont(editableFont)
            fontMetrics = painter.fontMetrics()
            if item.payload:
                text = item.payload
            else:
                text = _("(double-click to reword)") + " " + item.comment
        else:
            text = item.comment

        text = fontMetrics.elidedText(text, option.textElideMode, rect.width())
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
        if not opAbove and (op == RebaseOp.Fixup or op == RebaseOp.Squash):
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
            if op == RebaseOp.Fixup or op == RebaseOp.Squash:
                connectBelow = True
            break

        if startOp == RebaseOp.Fixup or startOp == RebaseOp.Squash:
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
