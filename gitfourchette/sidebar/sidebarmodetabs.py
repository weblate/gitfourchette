import logging

from gitfourchette.qt import *
from gitfourchette.settings import DEVDEBUG, qtIsNativeMacosStyle

_logger = logging.getLogger(__name__)


class _SidebarModeTabStyle(QProxyStyle):
    def drawControl(self, element: QStyle.ControlElement, option: QStyleOption, painter: QPainter, widget: QWidget):
        if element != QStyle.ControlElement.CE_TabBarTabLabel:
            super().drawControl(element, option, painter, widget)
            return

        assert element == QStyle.ControlElement.CE_TabBarTabLabel

        if not isinstance(option, QStyleOptionTab):
            # When the app is in the background, PyQt5 sometimes passes some
            # junk type here (QStyleOptionViewItem) even though the docs say
            # that CE_TabBarTabLabel corresponds to QStyleOptionTab.
            # Is this a bug in the binding?
            # (I've also seen it happen *once* with PyQt6...)
            if DEVDEBUG:
                _logger.warning(f"Unexpected QProxyStyle option: {type(option)}")
            super().drawControl(element, option, painter, widget)  # default to normal
            return

        assert isinstance(option, QStyleOptionTab)

        # On some themes like Breeze, active tab text may be raised by a couple pixels.
        # So use that as the center instead of option.rect.center().
        textRect: QRect = self.proxy().subElementRect(QStyle.SubElement.SE_TabBarTabText, option, widget)
        iconCenter = QPoint(option.rect.center().x(), textRect.center().y())

        icon: QIcon = option.icon
        iconSize = option.iconSize  # TODO: or just set a custom size like QSize(20,20)
        iconColor = painter.pen().color()
        iconRect = QRect(0, 0, iconSize.width(), iconSize.height())
        iconRect.moveCenter(iconCenter)

        dpr = widget.devicePixelRatioF()

        if QT5:
            maskPixmap = icon.pixmap(iconSize * dpr)
            maskPixmap.setDevicePixelRatio(dpr)
        else:
            maskPixmap = icon.pixmap(iconSize, dpr)

        colorPixmap = QPixmap(maskPixmap.size())
        colorPixmap.setDevicePixelRatio(dpr)
        colorPixmap.fill(Qt.GlobalColor.transparent)  # prime alpha channel
        colorPixmap.fill(iconColor)

        stencil = QPainter(colorPixmap)
        stencil.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        stencil.drawPixmap(0, 0, maskPixmap)
        stencil.end()

        painter.drawPixmap(iconRect, colorPixmap, colorPixmap.rect())


class SidebarModeTabs(QTabBar):
    def __init__(self, parent):
        super().__init__(parent)

        self.setObjectName("SidebarModeTabs")
        self.setExpanding(False)

        # Pass a string to the proxy's ctor, NOT QApplication.style() as this would transfer the ownership
        # of the style to the proxy!!!
        from gitfourchette import settings
        proxyStyle = _SidebarModeTabStyle(settings.prefs.qtStyle)
        self.setStyle(proxyStyle)

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
