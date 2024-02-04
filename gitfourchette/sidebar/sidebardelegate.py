from gitfourchette.qt import *
from gitfourchette.sidebar.sidebarmodel import SidebarModel, SidebarNode, EItem, UNINDENT_ITEMS, LEAF_ITEMS, ALWAYS_EXPAND


PE_EXPANDED = QStyle.PrimitiveElement.PE_IndicatorArrowDown
PE_COLLAPSED_LTR = QStyle.PrimitiveElement.PE_IndicatorArrowRight
PE_COLLAPSED_RTL = QStyle.PrimitiveElement.PE_IndicatorArrowLeft

# These metrics are a good compromise for Breeze, macOS, and Fusion.
EXPAND_TRIANGLE_WIDTH = 6
EXPAND_TRIANGLE_PADDING = 4


class SidebarDelegate(QStyledItemDelegate):
    def __init__(self, parent: QWidget):
        super().__init__(parent)

    @staticmethod
    def unindentRect(item: EItem, rect: QRect, indentation: int):
        if item not in UNINDENT_ITEMS:
            return
        unindentLevels = UNINDENT_ITEMS[item]
        unindentPixels = unindentLevels * indentation
        if QGuiApplication.isLeftToRight():
            rect.adjust(unindentPixels, 0, 0, 0)
        else:
            rect.adjust(0, 0, -unindentPixels, 0)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        """
        Draw custom branch indicator. The standard one is too cluttered in some
        themes, e.g. Breeze, so I've disabled it in style.qss.

        In the macOS theme, the default actually looks fine... but let's
        override it anyway for consistency with other platforms.
        """

        view: QTreeView = option.widget

        node = SidebarNode.fromIndex(index)
        item = node.kind

        # Don't draw spacers at all (Windows theme has mouse hover effect by default)
        if item == EItem.Spacer:
            return

        opt = QStyleOptionViewItem(option)

        SidebarDelegate.unindentRect(item, opt.rect, view.indentation())

        # Draw expanding triangle
        if item not in LEAF_ITEMS and item not in ALWAYS_EXPAND:
            rtl = view.isRightToLeft()

            opt2 = QStyleOptionViewItem(opt)
            r: QRect = opt2.rect

            if not rtl:
                r.adjust(-(EXPAND_TRIANGLE_WIDTH + EXPAND_TRIANGLE_PADDING), 0, 0, 0)  # args must be integers for pyqt5!
            else:
                r.adjust(r.width() + EXPAND_TRIANGLE_PADDING, 0, 0, 0)

            r.setWidth(EXPAND_TRIANGLE_WIDTH)

            # See QTreeView::drawBranches() in qtreeview.cpp for other interesting states
            opt2.state &= ~QStyle.StateFlag.State_MouseOver

            style: QStyle = view.style()
            if view.isExpanded(index):
                arrowPrimitive = PE_EXPANDED
            else:
                arrowPrimitive = PE_COLLAPSED_LTR if not rtl else PE_COLLAPSED_RTL
            style.drawPrimitive(arrowPrimitive, opt2, painter, view)

        super().paint(painter, opt, index)
