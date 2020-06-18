from PySide2.QtWidgets import *
from PySide2.QtGui import *
from PySide2.QtCore import *
from datetime import datetime
import settings
from Lanes import Lanes


XMargin = 4
ColW_Author = 16
ColW_Hash = settings.prefs.shortHashChars + 1
ColW_Date = 16
LaneW = 10
DEBUGRECTS = False


# différence entre QItemDelegate et QStyledItemDelegate?
class GraphDelegate(QItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)

    def paint(self, painter, option, index):
        # print("Render Index Row: " +  str(index.row()))
        # super(__class__, self).paint(painter, option, index)

        painter.save()

        palette: QPalette = option.palette
        pcg = QPalette.ColorGroup.Current if option.state & QStyle.State_HasFocus else QPalette.ColorGroup.Disabled

        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, palette.color(pcg, QPalette.ColorRole.Highlight))
            painter.setPen(palette.color(QPalette.ColorRole.HighlightedText))

        rect = QRect(option.rect)
        rect.setLeft(rect.left() + XMargin)
        rect.setRight(rect.right() - XMargin)
        if DEBUGRECTS: painter.drawRoundedRect(rect, 4, 4)

        # get font metrics before setting a custom font,
        # so that alignments are consistent in all commits regardless of bold or italic
        metrics = painter.fontMetrics()
        zw = metrics.width('0')

        if index.row() > 0:
            meta = index.data()

            message: str = meta.body.strip()
            newline = message.find('\n')
            if newline > -1:
                messageContinued = newline < len(message) - 1
                message = message[:newline]
                if messageContinued:
                    message += " [...]"

            data = {
                'hash': meta.hexsha[:settings.prefs.shortHashChars],
                'author': meta.authorEmail.split('@')[0],  # [:8],
                'date': datetime.fromtimestamp(meta.authorTimestamp).strftime(settings.prefs.shortTimeFormat),
                'message': message,
                'tags': meta.tags,
                'refs': meta.refs
            }

            assert meta.lane >= 0

            if meta.bold:
                painter.setFont(settings.boldFont)
        else:
            meta = None
            data = {
                'hash': "·" * settings.prefs.shortHashChars,
                'author': "",
                'date': "",
                'message': index.data(),
                'tags': [],
                'refs': []
            }
            painter.setFont(settings.alternateFont)

        # ------ Hash
        rect.setWidth(ColW_Hash * zw)
        if DEBUGRECTS: painter.drawRoundedRect(rect, 4, 4)
        charRect = QRect(rect.left(), rect.top(), zw, rect.height())
        painter.save()
        painter.setPen(palette.color(pcg, QPalette.ColorRole.PlaceholderText))
        for hashChar in data['hash']:
            painter.drawText(charRect, Qt.AlignCenter, hashChar)
            charRect.translate(zw, 0)
        painter.restore()

        # ------ Graph
        rect.setLeft(rect.right())
        if meta is not None:
            painter.save()
            painter.setRenderHints(QPainter.Antialiasing, True)

            x = rect.left() + LaneW / 2
            top = rect.top()
            bottom = rect.bottom()
            middle = (rect.top() + rect.bottom()) / 2

            painter.setPen(QPen(Qt.darkGray, 2))
            for lane, mask in enumerate(meta.laneData):
                if 0 != (mask & Lanes.STRAIGHT):
                    painter.drawLine(x + lane * LaneW, top, x + lane * LaneW, bottom)
                if 0 != (mask & Lanes.FORK_UP):
                    painter.drawLine(x + lane * LaneW, top, x + meta.lane * LaneW, middle)
                if 0 != (mask & Lanes.FORK_DOWN):
                    painter.drawLine(x + meta.lane * LaneW, middle, x + lane * LaneW, bottom)

            painter.setBrush(QColor(Qt.darkGray))
            painter.drawEllipse(QPoint(x + meta.lane * LaneW, middle), 2, 2)

            rect.setRight(x + LaneW * len(meta.laneData))
            painter.restore()

        # ------ tags
        for ref in data['refs']:
            painter.save()
            painter.setFont(settings.smallFont)
            painter.setPen(QColor(Qt.darkMagenta))
            rect.setLeft(rect.right())
            label = F"[{ref}] "
            rect.setWidth(settings.smallFontMetrics.width(label) + 1)
            painter.drawText(rect, label)
            painter.restore()
        for tag in data['tags']:
            painter.save()
            painter.setFont(settings.smallFont)
            painter.setPen(QColor(Qt.darkYellow))
            rect.setLeft(rect.right())
            label = F"[{tag}] "
            rect.setWidth(settings.smallFontMetrics.width(label) + 1)
            painter.drawText(rect, label)
            painter.restore()

        # ------ message
        if meta and not meta.hasLocal:
            painter.setPen(QColor(Qt.gray))
        rect.setLeft(rect.right())
        rect.setRight(option.rect.right() - (ColW_Author + ColW_Date) * zw - XMargin)
        mzg = metrics.elidedText(data['message'], Qt.ElideRight, rect.width())
        if DEBUGRECTS: painter.drawRoundedRect(rect, 4, 4)
        painter.drawText(rect, mzg)

        # ------ Author
        rect.setLeft(rect.right())
        rect.setWidth(ColW_Author * zw)
        if DEBUGRECTS: painter.drawRoundedRect(rect, 4, 4)
        painter.drawText(rect, data['author'])

        # ------ Date
        rect.setLeft(rect.right())
        rect.setWidth(ColW_Date * zw)
        if DEBUGRECTS: painter.drawRoundedRect(rect, 4, 4)
        painter.drawText(rect, data['date'])

        # ----------------
        painter.restore()
        pass  # QStyledItemDelegate.paint(self, painter, option, index)

    def sizeHint(self, option, index):
        # return QStyledItemDelegate.sizeHint(self, option, index)
        return QItemDelegate.sizeHint(self, option, index)
