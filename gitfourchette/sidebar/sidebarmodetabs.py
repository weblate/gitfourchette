from gitfourchette.qt import *


class _SidebarModeTabStyle(QProxyStyle):
    def drawControl(self, element: QStyle.ControlElement, option: QStyleOptionTab, painter: QPainter, widget: QWidget = None):
        icon = QIcon()

        if element == QStyle.ControlElement.CE_TabBarTabLabel:
            icon = QIcon(option.icon)
            option.icon = QIcon()  # draw without icon first
            option.text = ""  # and without text

        super().drawControl(element, option, painter, widget)

        if icon.isNull():
            return

        iconSize = QSize(option.iconSize)  # TODO: or just set a custom size like QSize(20,20)
        iconRect = QRect(0, 0, iconSize.width(), iconSize.height())
        iconRect.moveCenter(option.rect.center())

        iconMode = QIcon.Mode.Normal if (option.state & QStyle.StateFlag.State_Enabled) else QIcon.Mode.Disabled
        iconState = QIcon.State.On if (option.state & QStyle.StateFlag.State_Selected) else QIcon.State.Off
        pixmap = icon.pixmap(iconSize, iconMode, iconState)

        painter.drawPixmap(iconRect.x(), iconRect.y(), pixmap)


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

    def tabSizeHint(self, index):
        # Works best if "expanding" tabs are OFF.
        minW = int(self.width() / self.count())
        w = max(minW, 16)
        w = min(w, 40)
        # vanillaSize = QTabBar.tabSizeHint(self, index)
        return QSize(w, 40)
