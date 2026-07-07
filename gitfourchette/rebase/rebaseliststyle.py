# -----------------------------------------------------------------------------
# Copyright (C) 2026 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

from gitfourchette import settings
from gitfourchette.qt import *


class RebaseListStyle(QProxyStyle):
    """
    Provides a nicer-looking drop indicator for RebaseDialog's list view.
    """

    def __init__(self):
        # Don't pass application-wide QStyle to the constructor, otherwise
        # QProxyStyle will take ownership of it!
        style = settings.prefs.qtStyle
        super().__init__(style)

    def drawPrimitive(self, element: QStyle.PrimitiveElement, option: QStyleOption, painter: QPainter, widget: QWidget | None = None):
        if element == QStyle.PrimitiveElement.PE_IndicatorItemViewItemDrop and not option.rect.isNull():
            self.drawDropIndicator(option, painter, widget)
        else:
            super().drawPrimitive(element, option, painter, widget)

    def drawDropIndicator(self, option: QStyleOption, painter: QPainter, widget: QWidget | None = None):
        assert isinstance(widget, QAbstractScrollArea)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        xMargin = 0
        barH = 2
        triH = 16
        triW = 24
        triCurvature = .66
        outline = 4

        left     = option.rect.left() + xMargin
        leftTip  = left + triW
        leftCtl  = left+int(triW*(1-triCurvature))

        right    = left + widget.viewport().width() - xMargin*2
        rightTip = right-triW
        rightCtl = right-int(triW*(1-triCurvature))

        y = option.rect.center().y()
        yTriTop = y - triH//2
        yBarTop = y - barH//2
        yTriBot = y + triH//2
        yBarBot = y + barH//2

        color = option.palette.color(QPalette.ColorRole.Text)
        outlineColor = option.palette.color(QPalette.ColorRole.Base)
        outlineColor.setAlphaF(.75)

        path = QPainterPath()
        path.moveTo(left    , yTriTop)
        path.quadTo(leftCtl , yBarTop, leftTip, yBarTop)
        path.lineTo(rightTip, yBarTop)
        path.quadTo(rightCtl, yBarTop, right, yTriTop)
        path.lineTo(right   , yTriBot)
        path.quadTo(rightCtl, yBarBot, rightTip, yBarBot)
        path.lineTo(leftTip , yBarBot)
        path.quadTo(leftCtl , yBarBot, left, yTriBot)
        path.closeSubpath()

        painter.setPen(QPen(outlineColor, outline, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
        painter.drawPath(path)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawPath(path)
