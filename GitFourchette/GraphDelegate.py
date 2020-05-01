from PySide2.QtWidgets import *
from PySide2.QtGui import *
from PySide2.QtCore import *
import globals


ColW_Author = 18
ColW_Hash = 10
ColW_Date = 16


# différence entre QItemDelegate et QStyledItemDelegate?
class GraphDelegate(QItemDelegate):
    def __init__(self, parent=None):
        super(__class__, self).__init__(parent)

    def paint(self, painter, option, index):
        super(__class__, self).paint(painter, option, index)
        if index.row() == 0:  # Uncommitted changes
            return

        # print("Render Index Row: " +  str(index.row()))
        commit = index.data()
        data = {
            'hash': commit.hexsha[:7],
            'author': commit.author.email.split('@')[0],  # [:8],
            'date': commit.authored_datetime.strftime(globals.graphViewTimeFormat),
            'message': commit.message.split('\n')[0] or "¯\\_(ツ)_/¯"
        }
        painter.save()
        metrics = painter.fontMetrics()
        zw = metrics.width('e')
        if option.state & QStyle.State_Selected:
            painter.setPen(option.palette.color(QPalette.ColorRole.HighlightedText))
        # ------ message
        rect = QRect(option.rect)
        rect.setLeft(rect.left() + 5)
        rect.setRight(option.rect.width() - (ColW_Author + ColW_Hash + ColW_Date) * zw)
        mzg = metrics.elidedText(data['message'], Qt.ElideRight, rect.width())
        painter.drawText(rect, mzg)
        # ------ Author
        rect.setX(rect.right())
        rect.setWidth(ColW_Author * zw)
        painter.drawText(rect, data['author'])
        # ------ Hash
        # painter.setFont(monoFont)
        rect.setLeft(rect.right())
        nextX = rect.left() + ColW_Hash * zw
        rect.setWidth(zw)
        for c in data['hash']:
            painter.drawText(rect, Qt.AlignCenter, c)
            rect.setLeft(rect.left() + zw)
            rect.setWidth(zw)
        # ------ Date
        rect.setX(nextX)
        rect.setWidth(ColW_Date * zw)
        painter.drawText(rect, data['date'])
        # ----------------
        painter.restore()
        pass  # QStyledItemDelegate.paint(self, painter, option, index)

    def sizeHint(self, option, index):
        # return QStyledItemDelegate.sizeHint(self, option, index)
        return QItemDelegate.sizeHint(self, option, index)
