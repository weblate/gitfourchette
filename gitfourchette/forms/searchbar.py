import re

from gitfourchette.qt import *
from gitfourchette.toolbox import *
from gitfourchette.forms.ui_searchbar import Ui_SearchBar


SEARCH_PULSE_DELAY = 250
LIKELY_HASH_PATTERN = re.compile(r"[0-9A-Fa-f]{1,40}")


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
        return self.lineEdit.text()

    @property
    def lineEdit(self) -> QLineEdit:
        return self.ui.lineEdit

    @property
    def textChanged(self):
        return self.lineEdit.textChanged

    @property
    def buttons(self):
        return self.ui.forwardButton, self.ui.backwardButton, self.ui.closeButton

    def __init__(self, buddy: QWidget, help: str):
        super().__init__(buddy)

        self.setObjectName(f"SearchBar({buddy.objectName()})")
        self.buddy = buddy

        self.ui = Ui_SearchBar()
        self.ui.setupUi(self)

        self.lineEdit.setStyleSheet("border: 1px solid gray; border-radius: 5px;")
        self.lineEdit.setPlaceholderText(help)
        self.lineEdit.addAction(stockIcon("magnifying-glass"), QLineEdit.ActionPosition.LeadingPosition)
        self.lineEdit.textChanged.connect(self.onSearchTextChanged)

        self.ui.closeButton.clicked.connect(self.bail)
        self.ui.forwardButton.clicked.connect(self.searchNext)
        self.ui.backwardButton.clicked.connect(self.searchPrevious)

        self.ui.forwardButton.setIcon(stockIcon("go-down-search"))
        self.ui.backwardButton.setIcon(stockIcon("go-up-search"))
        self.ui.closeButton.setIcon(stockIcon("dialog-close"))

        for button in self.buttons:
            button.setMaximumHeight(1)

        appendShortcutToToolTip(self.ui.backwardButton, QKeySequence.StandardKey.FindPrevious)
        appendShortcutToToolTip(self.ui.forwardButton, QKeySequence.StandardKey.FindNext)
        appendShortcutToToolTip(self.ui.closeButton, Qt.Key.Key_Escape)

        self.searchTerm = ""
        self.searchTermLooksLikeHash = False

        self.searchPulseTimer = QTimer(self)
        self.searchPulseTimer.setSingleShot(True)
        self.searchPulseTimer.setInterval(SEARCH_PULSE_DELAY)
        self.searchPulseTimer.timeout.connect(self.searchPulse)

        tweakWidgetFont(self.lineEdit, 85)

    def keyPressEvent(self, event: QKeyEvent):
        if not self.lineEdit.hasFocus():
            super().keyPressEvent(event)

        elif event.key() in [Qt.Key.Key_Return, Qt.Key.Key_Enter]:
            self.lineEdit.selectAll()
            if not self.searchTerm:
                QApplication.beep()
            elif event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self.searchPrevious.emit()
            else:
                self.searchNext.emit()

        elif event.key() == Qt.Key.Key_Escape:
            self.bail()

        else:
            super().keyPressEvent(event)

    def popUp(self, forceSelectAll=False):
        wasHidden = self.isHidden()
        self.show()

        for button in self.buttons:
            button.setMaximumHeight(self.lineEdit.height())

        self.lineEdit.setFocus(Qt.FocusReason.PopupFocusReason)

        if forceSelectAll or wasHidden:
            self.lineEdit.selectAll()

    def bail(self):
        self.searchPulseTimer.stop()
        self.buddy.setFocus(Qt.FocusReason.PopupFocusReason)
        self.hide()

    def onSearchTextChanged(self, text: str):
        self.turnRed(False)
        self.searchTerm = text.strip().lower()

        if 0 < len(self.searchTerm) <= 40:
            self.searchTermLooksLikeHash = bool(re.match(LIKELY_HASH_PATTERN, text))

        if self.searchTerm:
            self.searchPulseTimer.start()
        else:
            self.searchPulseTimer.stop()

    def turnRed(self, red=True):
        wasRed = self.property("red") == "true"
        self.setProperty("red", "true" if red else "false")
        if wasRed ^ red:  # trigger stylesheet refresh
            self.setStyleSheet("* {}")
