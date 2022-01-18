from allqt import *
from widgets.sidebarentry import SidebarEntry
import settings


class SidebarDelegate(QStyledItemDelegate):
    def __init__(self, parent: QWidget):
        super().__init__(parent)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        view: QTreeView = self.parent()
        model: QStandardItemModel = index.model()
        data: SidebarEntry = index.data()

        opt = QStyleOptionViewItem(option)
        opt.rect.setLeft(20)

        if not index.parent().isValid():
            opt.font = QFont()
            opt.font.setBold(True)

        super().paint(painter, opt, index)

        if model.rowCount(index) > 0:
            opt = QStyleOptionViewItem(option)
            opt.rect.setLeft(0)
            opt.rect.setRight(20)

            style: QStyle = view.style()
            arrowPrimitive = QStyle.PE_IndicatorArrowDown if view.isExpanded(index) else QStyle.PE_IndicatorArrowRight
            style.drawPrimitive(arrowPrimitive, opt, painter, view)

    #def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
    #    return QSize(-1, 16)
