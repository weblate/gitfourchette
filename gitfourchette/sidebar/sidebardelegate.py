import enum

from gitfourchette.qt import *
from gitfourchette.sidebar.sidebarmodel import SidebarNode, SidebarModel, EItem, UNINDENT_ITEMS, ROLE_ICONKEY
from gitfourchette.toolbox import stockIcon

PE_EXPANDED = QStyle.PrimitiveElement.PE_IndicatorArrowDown
PE_COLLAPSED = QStyle.PrimitiveElement.PE_IndicatorArrowRight

# These metrics are a good compromise for Breeze, macOS, and Fusion.
EXPAND_TRIANGLE_WIDTH = 6
PADDING = 4
EYE_WIDTH = 16


class SidebarClickZone(enum.IntEnum):
    Invalid = 0
    Select = 1
    Expand = 2
    Hide = 3


class SidebarDelegate(QStyledItemDelegate):
    """
    Draws custom tree expand/collapse indicator arrows,
    and hide/show icons.
    """

    def __init__(self, parent: QWidget):
        super().__init__(parent)

    @staticmethod
    def unindentRect(item: EItem, rect: QRect, indentation: int):
        if item not in UNINDENT_ITEMS:
            return
        unindentLevels = UNINDENT_ITEMS[item]
        unindentPixels = unindentLevels * indentation
        return rect.adjust(unindentPixels, 0, 0, 0)

    @staticmethod
    def getClickZone(node: SidebarNode, rect: QRect, x: int):
        if node.kind == EItem.Spacer:
            return SidebarClickZone.Invalid
        elif node.mayHaveChildren() and x < rect.left():
            return SidebarClickZone.Expand
        elif node.canBeHidden() and x > rect.right() - EYE_WIDTH - PADDING:
            return SidebarClickZone.Hide
        else:
            return SidebarClickZone.Select

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        node = SidebarNode.fromIndex(index)

        # Don't draw spacers at all (Windows theme has mouse hover effect by default)
        if node.kind == EItem.Spacer:
            return

        view = option.widget
        sidebarModel: SidebarModel = view.sidebarModel
        style: QStyle = view.style()
        hasFocus = option.state & QStyle.StateFlag.State_HasFocus
        isSelected = option.state & QStyle.StateFlag.State_Selected
        colorGroup = QPalette.ColorGroup.Normal if hasFocus else QPalette.ColorGroup.Inactive
        nodeIsHidden = sidebarModel.isHidden(node)
        mouseOver = option.state & QStyle.StateFlag.State_Enabled and option.state & QStyle.StateFlag.State_MouseOver
        makeRoomForEye = nodeIsHidden or (mouseOver and node.canBeHidden())

        painter.save()
        option.showDecorationSelected = True  # ?

        # Unindent rect
        SidebarDelegate.unindentRect(node.kind, option.rect, view.indentation())

        # Draw expand/collapse triangle.
        if node.mayHaveChildren() and not node.wantForceExpand():
            opt2 = QStyleOptionViewItem(option)
            opt2.rect.adjust(-(EXPAND_TRIANGLE_WIDTH + PADDING), 0, 0, 0)  # args must be integers for pyqt5!
            opt2.rect.setWidth(EXPAND_TRIANGLE_WIDTH)

            # See QTreeView::drawBranches() in qtreeview.cpp for other interesting states
            opt2.state &= ~QStyle.StateFlag.State_MouseOver
            arrowPrimitive = PE_EXPANDED if view.isExpanded(index) else PE_COLLAPSED
            style.drawPrimitive(arrowPrimitive, opt2, painter, view)

        # Draw control background
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, option, painter, option.widget)

        # Adjust contents
        option.rect.adjust(PADDING, 0, -PADDING, 0)

        # Set highlighted text color if this item is selected
        iconCLUT = ""
        if isSelected:
            hlColor = option.palette.color(colorGroup, QPalette.ColorRole.HighlightedText)
            painter.setPen(hlColor)
            iconCLUT = f"gray={hlColor.name()}"

        # Draw decoration icon
        iconWidth = option.decorationSize.width()
        iconKey = index.data(ROLE_ICONKEY)
        if iconKey:
            r = QRect(option.rect)
            r.setWidth(iconWidth)
            icon = stockIcon(iconKey, iconCLUT)
            icon.paint(painter, r, option.decorationAlignment)
            option.rect.adjust(r.width() + PADDING*150//100, 0, 0, 0)

        # Draw text
        textRect = QRect(option.rect)
        if makeRoomForEye:
            textRect.adjust(0, 0, -EYE_WIDTH, 0)
        font: QFont = index.data(Qt.ItemDataRole.FontRole) or option.font
        painter.setFont(font)
        fullText = index.data(Qt.ItemDataRole.DisplayRole)
        text = painter.fontMetrics().elidedText(fullText, option.textElideMode, textRect.width())
        painter.drawText(textRect, option.displayAlignment, text)

        # Draw eye
        if makeRoomForEye:
            r = QRect(option.rect)
            r.setLeft(textRect.right())
            r.setWidth(EYE_WIDTH)
            eyeIconName = "view-hidden" if nodeIsHidden else "view-visible"
            eyeIcon = stockIcon(eyeIconName, iconCLUT)
            eyeIcon.paint(painter, r)

        painter.restore()
