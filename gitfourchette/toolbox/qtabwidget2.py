from gitfourchette.qt import *
from gitfourchette import settings


class QTabBar2(QTabBar):
    tabMiddleClicked = Signal(int)
    tabDoubleClicked = Signal(int)
    visibilityChanged = Signal(bool)
    wheelDelta = Signal(QPoint)

    middleClickedIndex: int
    doubleClickedIndex: int

    def __init__(self, parent: QWidget):
        super().__init__(parent)

        self.middleClickedIndex = -1
        self.doubleClickedIndex = -1

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.MiddleButton:
            self.middleClickedIndex = self.tabAt(event.pos())
        else:
            self.middleClickedIndex = -1
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.doubleClickedIndex = self.tabAt(event.pos())
        else:
            self.doubleClickedIndex = -1

        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        # Block double-click signal if mouse moved before releasing button
        self.doubleClickedIndex = -1
        super().mouseMoveEvent(event)

    def wheelEvent(self, event: QWheelEvent):
        self.wheelDelta.emit(event.angleDelta())

        # DO NOT forward mouse wheel events to superclass
        # (avoid default Qt behavior that switches tabs via scroll wheel)
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.buttons() != Qt.MouseButton.NoButton:
            # Signals will only fire if clicking a single button at a time
            pass

        elif event.button() == Qt.MouseButton.MiddleButton:
            i = self.tabAt(event.pos())
            if i >= 0 and i == self.middleClickedIndex:
                self.tabMiddleClicked.emit(i)

        elif event.button() == Qt.MouseButton.LeftButton:
            i = self.tabAt(event.pos())
            if i >= 0 and i == self.doubleClickedIndex:
                self.tabDoubleClicked.emit(i)

        self.middleClickedIndex = -1
        self.doubleClickedIndex = -1

        super().mouseReleaseEvent(event)

    def setVisible(self, visible: bool):
        """Forward setVisible to parent scroll area"""
        super().setVisible(visible)
        self.visibilityChanged.emit(visible)


class QTabWidget2(QWidget):
    currentChanged: Signal = Signal(int)
    tabCloseRequested: Signal = Signal(int)
    tabDoubleClicked: Signal = Signal(int)
    tabContextMenuRequested: Signal = Signal(QPoint, int)

    currentWidgetChanged = Signal()
    """Emitted when the displayed widget is actually changed (in contrast to
    currentChanged, which is emitted even when dragging the foreground tab)."""

    def __init__(self, parent):
        super().__init__(parent)

        self.stacked = QStackedWidget(self)
        self.shadowCurrentWidget = None

        self.tabScrollArea = QScrollArea(parent=self, widgetResizable=True)
        self.tabScrollArea.setFrameStyle(QFrame.Shape.NoFrame)
        self.tabScrollArea.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tabScrollArea.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tabScrollArea.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)  # works ok but tries to expand the window width when opening a new tab?

        self.tabs = QTabBar2(self.tabScrollArea)
        self.tabs.tabMoved.connect(self.onTabMoved)
        self.tabs.currentChanged.connect(self.onCurrentChanged)
        self.tabs.tabCloseRequested.connect(self.tabCloseRequested)
        self.tabs.tabMiddleClicked.connect(self.tabCloseRequested)
        self.tabs.tabDoubleClicked.connect(self.tabDoubleClicked)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)  # dramatically improves the tabs' appearance on macOS
        self.tabs.setUsesScrollButtons(False)  # needed with scroll area

        self.tabScrollArea.setWidget(self.tabs)
        self.tabs.visibilityChanged.connect(self.tabScrollArea.setVisible)
        self.tabs.wheelDelta.connect(self.scrollTabs)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.tabScrollArea)
        layout.addWidget(self.stacked)
        self.setLayout(layout)

        self.tabs.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tabs.customContextMenuRequested.connect(self.onCustomContextMenuRequested)

        self.refreshPrefs()

    def refreshPrefs(self):
        self.tabs.setExpanding(settings.prefs.tabs_expanding)
        self.tabs.setAutoHide(settings.prefs.tabs_autoHide)
        self.tabs.setTabsClosable(settings.prefs.tabs_closeButton)
        self.tabs.update()
        self.syncBarSize()

    def onCustomContextMenuRequested(self, localPoint: QPoint):
        globalPoint = self.tabs.mapToGlobal(localPoint)
        index = self.tabs.tabAt(localPoint)
        self.tabContextMenuRequested.emit(globalPoint, index)

    def onTabMoved(self, fromIndex: int, toIndex: int):
        # Keep QStackedWidget in sync with QTabBar
        w = self.stacked.widget(fromIndex)
        self.stacked.removeWidget(w)
        self.stacked.insertWidget(toIndex, w)

    def onCurrentChanged(self, i: int):
        # Keep QStackedWidget in sync with QTabBar
        self.stacked.setCurrentIndex(i)

        # See if we should emit the currentWidgetChanged signal
        currentWidget = self.currentWidget()
        if currentWidget is not self.shadowCurrentWidget:
            self.shadowCurrentWidget = currentWidget
            self.currentWidgetChanged.emit()

        # Forward signal
        self.currentChanged.emit(i)

    def addTab(self, w: QWidget, name: str) -> int:
        i1 = self.stacked.addWidget(w)
        i2 = self.tabs.addTab(name)
        self.syncBarSize()
        assert i1 == i2
        return i1

    def insertTab(self, index: int, w: QWidget, name: str) -> int:
        i1 = self.stacked.insertWidget(index, w)
        i2 = self.tabs.insertTab(index, name)
        self.syncBarSize()
        assert i1 == i2
        return i1

    def setCurrentIndex(self, i: int):
        self.tabs.setCurrentIndex(i)
        self.stacked.setCurrentIndex(i)

    def indexOf(self, widget: QWidget):
        return self.stacked.indexOf(widget)

    def widget(self, i: int):
        return self.stacked.widget(i)

    def currentIndex(self) -> int:
        return self.stacked.currentIndex()

    def setTabText(self, i: int, text: str):
        self.tabs.setTabText(i, text)

    def setTabTooltip(self, i: int, toolTip: str):
        self.tabs.setTabToolTip(i, toolTip)

    def currentWidget(self) -> QWidget:
        return self.stacked.currentWidget()

    def count(self) -> int:
        return self.stacked.count()

    def removeTab(self, i: int):
        widget = self.stacked.widget(i)
        # remove widget from stacked view _before_ removing the tab,
        # because removing the tab may send a tab change event
        self.stacked.removeWidget(widget)
        self.tabs.removeTab(i)
        self.syncBarSize()

    def widgets(self):
        for i in range(self.stacked.count()):
            yield self.stacked.widget(i)

    def syncBarSize(self):
        h = self.tabs.sizeHint().height()
        if h != 0:
            self.tabScrollArea.setFixedHeight(self.tabs.sizeHint().height())

    def scrollTabs(self, delta: QPoint):
        scrollBar = self.tabScrollArea.horizontalScrollBar()
        # TODO: Horizontal mouse scrolling?
        scrollBar.setValue(scrollBar.value() - delta.y())
