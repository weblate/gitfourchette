from gitfourchette.qt import *
from gitfourchette.sidebar.sidebarmodel import SidebarModel, EItem, UNINDENT_ITEMS, LEAF_ITEMS


PE_EXPANDED = QStyle.PrimitiveElement.PE_IndicatorArrowDown
PE_COLLAPSED = QStyle.PrimitiveElement.PE_IndicatorArrowRight

# These metrics are a good compromise for Breeze, macOS, and Fusion.
EXPAND_TRIANGLE_WIDTH = 6
EXPAND_TRIANGLE_PADDING = 4


class SidebarDelegate(QStyledItemDelegate):
    def __init__(self, parent: QWidget):
        super().__init__(parent)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        """
        Draw custom branch indicator. The standard one is too cluttered in some
        themes, e.g. Breeze, so I've disabled it in style.qss.

        In the macOS theme, the default actually looks fine... but let's
        override it anyway for consistency with other platforms.
        """

        view: QTreeView = option.widget
        item = SidebarModel.unpackItem(index)

        # Don't draw spacers at all (Windows theme has mouse hover effect by default)
        if item == EItem.Spacer:
            return

        opt = QStyleOptionViewItem(option)

        if item in UNINDENT_ITEMS:
            unindentLevels = UNINDENT_ITEMS[item]
            unindentPixels = unindentLevels * view.indentation()
            opt.rect.adjust(unindentPixels, 0, 0, 0)

        # Draw expanding triangle
        if item not in LEAF_ITEMS:
            opt2 = QStyleOptionViewItem(opt)
            r: QRect = opt2.rect

            r.adjust(-EXPAND_TRIANGLE_WIDTH - EXPAND_TRIANGLE_PADDING, 0, 0, 0)  # args must be integers for pyqt5!
            r.setWidth(EXPAND_TRIANGLE_WIDTH)

            # See QTreeView::drawBranches() in qtreeview.cpp for other interesting states
            opt2.state &= ~QStyle.StateFlag.State_MouseOver

            style: QStyle = view.style()
            arrowPrimitive = PE_EXPANDED if view.isExpanded(index) else PE_COLLAPSED
            # arrowPrimitive = QStyle.PrimitiveElement.PE_IndicatorSpinPlus
            style.drawPrimitive(arrowPrimitive, opt2, painter, view)

        super().paint(painter, opt, index)
