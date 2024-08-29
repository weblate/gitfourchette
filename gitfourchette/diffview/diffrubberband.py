from gitfourchette import colors
from gitfourchette.qt import *
from gitfourchette.toolbox import isDarkTheme


class DiffRubberBand(QWidget):
    def paintEvent(self, event: QPaintEvent):
        # Don't inherit QRubberBand (pen thickness ignored on Linux!)
        RX = 12  # rounded rect x radius
        RY = 4  # rounded rect y radius
        T = 4  # thickness
        HT = T//2  # half thickness
        CT = 2  # clipped thickness

        painter = QPainter(self)
        rect: QRect = self.rect().marginsRemoved(QMargins(HT, HT, HT, HT))

        penColor = colors.teal if isDarkTheme() else colors.blue
        pen = QPen(penColor, T)
        painter.setPen(pen)

        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setClipRect(rect.marginsAdded(QMargins(HT, CT-HT, HT, CT-HT)))

        path = QPainterPath()
        path.addRoundedRect(QRectF(rect), RX, RY, Qt.SizeMode.AbsoluteSize)
        painter.drawPath(path)
