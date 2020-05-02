from PySide2.QtWidgets import *
from PySide2.QtGui import *
from PySide2.QtCore import *
import globals
import git


XMargin = 4
ColW_Author = 16
ColW_Hash = globals.shortHashChars + 1
ColW_Date = 16
DEBUGRECTS = False


# différence entre QItemDelegate et QStyledItemDelegate?
class GraphDelegate(QItemDelegate):
    def __init__(self, parent=None):
        super(__class__, self).__init__(parent)

    def paint(self, painter, option, index):
        # print("Render Index Row: " +  str(index.row()))
        # super(__class__, self).paint(painter, option, index)

        painter.save()
        metrics = painter.fontMetrics()
        zw = metrics.width('e')

        palette: QPalette = option.palette
        pcg = QPalette.ColorGroup.Current if option.state & QStyle.State_HasFocus else QPalette.ColorGroup.Disabled

        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, palette.color(pcg, QPalette.ColorRole.Highlight))
            painter.setPen(palette.color(QPalette.ColorRole.HighlightedText))

        rect = QRect(option.rect)
        rect.setLeft(rect.left() + XMargin)
        rect.setRight(rect.right() - XMargin)
        if DEBUGRECTS: painter.drawRoundedRect(rect, 4, 4)

        if index.row() > 0:
            bundle = index.data()
            commit: git.Commit = bundle.commit
            message: str = commit.message.strip()

            newline = message.find('\n')
            if newline > -1:
                messageContinued = newline < len(message) - 1
                message = message[:newline]
                if messageContinued:
                    message += " [...]"

            data = {
                'hash': commit.hexsha[:globals.shortHashChars],
                'author': commit.author.email.split('@')[0],  # [:8],
                'date': commit.authored_datetime.strftime(globals.graphViewTimeFormat),
                'message': message,
                'tags': bundle.tags,
                'refs': bundle.refs
            }
        else:
            data = {
                'hash': "·" * globals.shortHashChars,
                'author': "",
                'date': "",
                'message': index.data(),
                'tags': [],
                'refs': []
            }
            painter.setFont(globals.alternateFont)

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

        # ------ tags
        for tag in data['tags'] + data['refs']:
            painter.save()
            painter.setFont(globals.smallFont)
            rect.setLeft(rect.right())
            label = F"[{tag}] "
            rect.setWidth(globals.smallFontMetrics.width(label) + 1)
            painter.drawText(rect, label)
            painter.restore()

        # ------ message
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
