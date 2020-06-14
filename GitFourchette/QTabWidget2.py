from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *

import settings


class QTabBar2(QTabBar):
    def __init__(self, parent):
        super().__init__(parent)
        self.middleClickedIndex = -1

    """
    def contextMenuEvent(self, event):
        self.contextIndex = self.tabAt(event.pos())
        print(self.contextIndex)
    """

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MidButton:
            self.middleClickedIndex = self.tabAt(event.pos())
        else:
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MidButton:
            i = self.tabAt(event.pos())
            if i >= 0 and i == self.middleClickedIndex:
                self.tabCloseRequested.emit(i)
        else:
            super().mouseReleaseEvent(event)


class QTabWidget2(QWidget):
    tabCloseRequested: Signal = Signal(int)

    def __init__(self, parent):
        super().__init__(parent)

        self.stacked = QStackedWidget(self)

        self.tabs = QTabBar2(self)#(self)
        self.tabs.tabMoved.connect(self.onTabMoved)
        self.tabs.currentChanged.connect(self.stacked.setCurrentIndex)
        self.tabs.tabCloseRequested.connect(self.tabCloseRequested)
        self.tabs.setMovable(True)
        self.tabs.setExpanding(settings.prefs.tabs_expanding)
        self.tabs.setAutoHide(settings.prefs.tabs_autoHide)
        self.tabs.setTabsClosable(settings.prefs.tabs_closeButton)

        self.previousMiddleIndex = -1
        #self.tabs.installEventFilter(self)

        layout = QVBoxLayout()
        layout.setMargin(0)
        layout.setSpacing(0)
        layout.addWidget(self.tabs)
        layout.addWidget(self.stacked)
        self.setLayout(layout)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if (watched == self.tabs and
                event.type() in [QEvent.MouseButtonPress, QEvent.MouseButtonRelease] and event.button() == Qt.MidButton):
            tabIndex = self.tabs.tabAt(event.pos())
            if event.type() == QEvent.MouseButtonPress:
                self.previousMiddleIndex = tabIndex
            else:
                if tabIndex != -1 and tabIndex == self.previousMiddleIndex:
                    self.tabs.tabCloseRequested.emit(tabIndex)
                self.previousMiddleIndex = -1
            return True
        else:
            return False

    def onTabMoved(self, fromIndex: int, toIndex: int):
        w = self.stacked.widget(fromIndex)
        self.stacked.removeWidget(w)
        self.stacked.insertWidget(toIndex, w)

    def addTab(self, w: QWidget, name: str):
        i1 = self.stacked.addWidget(w)
        i2 = self.tabs.addTab(name)
        assert i1 == i2
        return i1

    def setCurrentIndex(self, i: int):
        self.tabs.setCurrentIndex(i)
        self.stacked.setCurrentIndex(i)

    def widget(self, i: int):
        return self.stacked.widget(i)

    def currentIndex(self) -> int:
        return self.stacked.currentIndex()

    def currentWidget(self) -> QWidget:
        return self.stacked.currentWidget()

    def count(self) -> int:
        return self.stacked.count()

    def removeTab(self, i: int, destroy: bool):
        widget = self.stacked.widget(i)
        # remove widget from stacked view _before_ removing the tab,
        # because removing the tab may send a tab change event
        self.stacked.removeWidget(widget)
        self.tabs.removeTab(i)
        if destroy:
            # QStackedWidget does not delete the widget in removeWidget, so we must do it manually.
            widget.deleteLater()
