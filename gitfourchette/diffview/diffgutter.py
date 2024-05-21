from __future__ import annotations

from typing import TYPE_CHECKING

from gitfourchette import settings
from gitfourchette.qt import *
from gitfourchette.toolbox import *

if TYPE_CHECKING:
    from gitfourchette.diffview.diffview import DiffView


class DiffGutter(QWidget):
    """
    Line number gutter for DiffView
    (inspired by https://doc.qt.io/qt-5/qtwidgets-widgets-codeeditor-example.html)
    """

    diffView: DiffView
    paddingString: str

    def __init__(self, parent):
        super().__init__(parent)
        self.diffView = parent
        self.paddingString = ""

        cursorDpr = 1 if FREEDESKTOP else 4  # On Linux, Qt doesn't seem to support cursors at non-1 DPR
        cursorPix = QPixmap(f"assets:icons/right_ptr@{cursorDpr}x")
        cursorPix.setDevicePixelRatio(cursorDpr)
        flippedCursor = QCursor(cursorPix, hotX=19, hotY=5)
        self.setCursor(flippedCursor)

        # Enable customContextMenuRequested signal
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

    def setMaxLineNumber(self, lineNumber: int):
        if lineNumber == 0:
            maxDigits = 0
        else:
            maxDigits = len(str(lineNumber))
        self.paddingString = "0" * (2 * maxDigits + 2)

    def calcWidth(self) -> int:
        return self.fontMetrics().horizontalAdvance(self.paddingString)

    def onParentUpdateRequest(self, rect: QRect, dy: int):
        if dy != 0:
            self.scroll(0, dy)
        else:
            self.update(0, rect.y(), self.width(), rect.height())

    def sizeHint(self) -> QSize:
        return QSize(self.calcWidth(), 0)

    def wheelEvent(self, event: QWheelEvent):
        # Forward mouse wheel to parent widget
        self.parentWidget().wheelEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        # Double click to select clump of lines
        if event.button() == Qt.MouseButton.LeftButton:
            self.diffView.selectClumpOfLinesAt(clickPoint=event.pos())

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self.diffView.selectWholeLinesTo(event.pos())
            else:
                self.diffView.selectWholeLineAt(event.pos())

    def mouseMoveEvent(self, event: QMouseEvent):
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.diffView.selectWholeLinesTo(event.pos())

    def paintEvent(self, event: QPaintEvent):
        diffView = self.diffView
        painter = QPainter(self)
        painter.setFont(self.font())

        # Set up colors
        palette = self.palette()
        themeBG = palette.color(QPalette.ColorRole.Base)  # standard theme background color
        themeFG = palette.color(QPalette.ColorRole.Text)  # standard theme foreground color
        if isDarkTheme(palette):
            gutterColor = themeBG.darker(105)  # light theme
        else:
            gutterColor = themeBG.lighter(140)  # dark theme
        lineColor = QColor(*themeFG.getRgb()[:3], 80)
        textColor = QColor(*themeFG.getRgb()[:3], 128)

        # Gather some metrics
        paintRect = event.rect()
        gutterRect = self.rect()
        fontHeight = self.fontMetrics().height()

        # Clip painting to QScrollArea viewport rect (don't draw beneath horizontal scroll bar)
        vpRect = diffView.viewport().rect()
        vpRect.setWidth(paintRect.width())  # vpRect is adjusted by gutter width, so undo this
        paintRect = paintRect.intersected(vpRect)
        painter.setClipRect(paintRect)

        # Draw background
        painter.fillRect(paintRect, gutterColor)

        # Draw vertical separator line
        painter.fillRect(gutterRect.x() + gutterRect.width() - 1, paintRect.y(), 1, paintRect.height(), lineColor)

        block: QTextBlock = diffView.firstVisibleBlock()
        blockNumber = block.blockNumber()
        top = round(diffView.blockBoundingGeometry(block).translated(diffView.contentOffset()).top())
        bottom = top + round(diffView.blockBoundingRect(block).height())

        # Draw line numbers and hunk separator lines
        if settings.prefs.colorblind:
            noOldPlaceholder = "+"
            noNewPlaceholder = "-"
        else:
            noOldPlaceholder = "·"
            noNewPlaceholder = "·"

        painter.setPen(textColor)
        while block.isValid() and top <= paintRect.bottom():
            if blockNumber >= len(diffView.lineData):
                break

            ld = diffView.lineData[blockNumber]
            if block.isVisible() and bottom >= paintRect.top():
                if ld.diffLine:
                    # Draw line numbers
                    old = str(ld.diffLine.old_lineno) if ld.diffLine.old_lineno > 0 else noOldPlaceholder
                    new = str(ld.diffLine.new_lineno) if ld.diffLine.new_lineno > 0 else noNewPlaceholder

                    colW = (gutterRect.width() - 4) // 2
                    painter.drawText(0, top, colW, fontHeight, Qt.AlignmentFlag.AlignRight, old)
                    painter.drawText(colW, top, colW, fontHeight, Qt.AlignmentFlag.AlignRight, new)
                else:
                    # Draw hunk separator horizontal line
                    painter.fillRect(0, round((top+bottom)/2), gutterRect.width()-1, 1, lineColor)

            block = block.next()
            top = bottom
            bottom = top + round(diffView.blockBoundingRect(block).height())
            blockNumber += 1

        painter.end()
