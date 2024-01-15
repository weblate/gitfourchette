from gitfourchette.qt import *
from gitfourchette.settings import qtIsNativeMacosStyle


class _SidebarModeTabStyle(QProxyStyle):
    def drawControl(self, element: QStyle.ControlElement, option: QStyleOptionTab, painter: QPainter, widget: QWidget):
        if element != QStyle.ControlElement.CE_TabBarTabLabel:
            super().drawControl(element, option, painter, widget)
            return

        painter.save()

        # On some themes like Breeze, active tab text may be raised by a couple pixels.
        # So use that as the center instead of option.rect.center().
        textRect: QRect = self.proxy().subElementRect(QStyle.SubElement.SE_TabBarTabText, option, widget)
        iconCenter = QPoint(option.rect.center().x(), textRect.center().y())

        icon: QIcon = option.icon
        iconSize = option.iconSize  # TODO: or just set a custom size like QSize(20,20)
        iconColor = painter.pen().color()
        iconRect = QRect(0, 0, iconSize.width(), iconSize.height())
        iconRect.moveCenter(iconCenter)

        maskPixmap = icon.pixmap(iconSize)
        colorPixmap = QPixmap(iconSize)
        colorPixmap.fill(Qt.GlobalColor.transparent)  # prime alpha channel
        colorPixmap.fill(iconColor)
        stencil = QPainter(colorPixmap)
        stencil.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        stencil.drawPixmap(0, 0, maskPixmap)
        stencil.end()
        painter.drawPixmap(iconRect.x(), iconRect.y(), colorPixmap)

        painter.restore()


class SidebarModeTabs(QTabBar):
    def __init__(self, parent):
        super().__init__(parent)

        self.setObjectName("SidebarModeTabs")
        self.setExpanding(False)

        # Pass a string to the proxy's ctor, NOT QApplication.style() as this would transfer the ownership
        # of the style to the proxy!!!
        from gitfourchette import settings
        self.proxyStyle = _SidebarModeTabStyle(settings.prefs.qtStyle)
        self.setStyle(self.proxyStyle)

        self.setMinimumWidth(4*16)

        if qtIsNativeMacosStyle():
            self.setDrawBase(False)

    def tabSizeHint(self, index):
        # Works best if "expanding" tabs are OFF.
        vanillaSize = QTabBar.tabSizeHint(self, index)
        count = self.count()
        if count == 0:  # avoid div by zero
            return vanillaSize

        minW = int(self.width() / count)
        w = max(minW, 16)
        w = min(w, 60)
        h = vanillaSize.height()
        return QSize(w, h)
