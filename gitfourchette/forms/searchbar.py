from gitfourchette.qt import *
from gitfourchette.toolbox import *
from gitfourchette.forms.ui_searchbar import Ui_SearchBar


SEARCH_PULSE_DELAY = 250


class SearchBar(QWidget):
    searchNext = Signal()
    searchPrevious = Signal()
    searchPulse = Signal()

    searchTerm: str
    "Sanitized search term (lowercase, stripped whitespace)"

    searchTermLooksLikeHash: bool
    "True if the search term looks like the start of a 40-character SHA-1 hash"

    searchPulseTimer: QTimer

    @property
    def rawSearchTerm(self):
        return self.ui.lineEdit.text()

    def __init__(self, parent: QWidget, help: str):
        super().__init__(parent)

        self.ui = Ui_SearchBar()
        self.ui.setupUi(self)

        self.ui.lineEdit.setStyleSheet("border: 1px solid gray; border-radius: 5px;")
        self.ui.lineEdit.setPlaceholderText("🔍 " + help)
        self.ui.closeButton.clicked.connect(self.bail)

        self.ui.forwardButton.clicked.connect(self.searchNext)
        self.ui.backwardButton.clicked.connect(self.searchPrevious)

        self.ui.lineEdit.textChanged.connect(self.onSearchTextChanged)

        self.ui.forwardButton.setIcon(stockIcon("go-down-search"))
        self.ui.backwardButton.setIcon(stockIcon("go-up-search"))
        self.ui.closeButton.setIcon(stockIcon("dialog-close"))

        appendShortcutToToolTip(self.ui.backwardButton, QKeySequence.StandardKey.FindPrevious)
        appendShortcutToToolTip(self.ui.forwardButton, QKeySequence.StandardKey.FindNext)
        appendShortcutToToolTip(self.ui.closeButton, Qt.Key.Key_Escape)

        self.searchTerm = ""
        self.searchTermLooksLikeHash = False

        self.searchPulseTimer = QTimer(self)
        self.searchPulseTimer.setSingleShot(True)
        self.searchPulseTimer.setInterval(SEARCH_PULSE_DELAY)
        self.searchPulseTimer.timeout.connect(self.searchPulse)

    @property
    def textChanged(self):
        return self.ui.lineEdit.textChanged

    def snapToParent(self):
        pw: QWidget = self.parentWidget()
        assert isinstance(pw, QAbstractScrollArea), "search bar parent must be QAbstractScrollArea"

        x = pw.width() - self.width() - pw.frameWidth()
        y = pw.frameWidth()

        if pw.verticalScrollBar().isVisible():
            x -= pw.verticalScrollBar().width()

        self.move(x, y)

    def keyPressEvent(self, event: QKeyEvent):
        if not self.ui.lineEdit.hasFocus():
            super().keyPressEvent(event)

        elif event.key() in [Qt.Key.Key_Return, Qt.Key.Key_Enter]:
            event.accept()
            self.ui.lineEdit.selectAll()
            if not self.searchTerm:
                QApplication.beep()
            elif event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self.searchPrevious.emit()
            else:
                self.searchNext.emit()

        elif event.key() == Qt.Key.Key_Escape:
            event.accept()
            self.bail()

    def popUp(self, forceSelectAll=False):
        wasHidden = self.isHidden()
        # TODO: if wasn't hidden, save whoever had focus, and restore focus on it (not necessarily parent()) in bail()
        self.show()
        self.snapToParent()
        self.ui.lineEdit.setFocus(Qt.FocusReason.PopupFocusReason)
        if forceSelectAll or wasHidden:
            self.ui.lineEdit.selectAll()

    def bail(self):
        self.searchPulseTimer.stop()
        self.parentWidget().setFocus(Qt.FocusReason.PopupFocusReason)
        self.hide()

    def onSearchTextChanged(self, text: str):
        self.searchTerm = text.strip().lower()

        if 0 < len(self.searchTerm) < 40:
            try:
                int(self.searchTerm, 16)
                self.searchTermLooksLikeHash = True
            except ValueError:
                self.searchTermLooksLikeHash = False

        if self.searchTerm:
            self.searchPulseTimer.start()
        else:
            self.searchPulseTimer.stop()
