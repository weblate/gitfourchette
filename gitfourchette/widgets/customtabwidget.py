from gitfourchette.qt import *
from gitfourchette import settings


class CustomTabBar(QTabBar):
    def __init__(self, parent):
        super().__init__(parent)
        self.middleClickedIndex = -1

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MiddleButton:
            self.middleClickedIndex = self.tabAt(event.pos())
        else:
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MiddleButton:
            i = self.tabAt(event.pos())
            if i >= 0 and i == self.middleClickedIndex:
                self.tabCloseRequested.emit(i)
        else:
            super().mouseReleaseEvent(event)


class CustomTabWidget(QWidget):
    tabCloseRequested: Signal = Signal(int)
    tabContextMenuRequested: Signal = Signal(QPoint, int)

    def __init__(self, parent):
        super().__init__(parent)

        self.stacked = QStackedWidget(self)

        self.tabs = CustomTabBar(self)
        self.tabs.tabMoved.connect(self.onTabMoved)
        self.tabs.currentChanged.connect(self.stacked.setCurrentIndex)
        self.tabs.tabCloseRequested.connect(self.tabCloseRequested)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)  # dramatically improves the tabs' appearance on macOS

        self.previousMiddleIndex = -1

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.tabs)
        layout.addWidget(self.stacked)
        self.setLayout(layout)

        self.tabs.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tabs.customContextMenuRequested.connect(self.onCustomContextMenuRequested)

        self.refreshPrefs()

    def refreshPrefs(self):
        self.tabs.setExpanding(settings.prefs.tabs_expanding)
        self.tabs.setAutoHide(settings.prefs.tabs_autoHide)
        self.tabs.setTabsClosable(settings.prefs.tabs_closeButton)

    def onCustomContextMenuRequested(self, localPoint: QPoint):
        globalPoint = self.tabs.mapToGlobal(localPoint)
        index = self.tabs.tabAt(localPoint)
        self.tabContextMenuRequested.emit(globalPoint, index)

    def onTabMoved(self, fromIndex: int, toIndex: int):
        w = self.stacked.widget(fromIndex)
        self.stacked.removeWidget(w)
        self.stacked.insertWidget(toIndex, w)

    def addTab(self, w: QWidget, name: str, toolTip: str = None):
        i1 = self.stacked.addWidget(w)
        i2 = self.tabs.addTab(name)
        if toolTip:
            self.tabs.setTabToolTip(i2, toolTip)
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
