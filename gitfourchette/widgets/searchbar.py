from gitfourchette.qt import *
from gitfourchette.widgets.ui_searchwidget import Ui_SearchWidget


class SearchBar(QWidget):
    searchNext = Signal()
    searchPrevious = Signal()

    def __init__(self, parent: QWidget, help: str):
        super().__init__(parent)

        self.ui = Ui_SearchWidget()
        self.ui.setupUi(self)

        self.ui.lineEdit.setStyleSheet("border: 1px solid gray; border-radius: 5px;")
        self.ui.lineEdit.setPlaceholderText("🔍 " + help)
        self.ui.closeButton.clicked.connect(self.bail)

        self.ui.forwardButton.clicked.connect(self.searchNext)
        self.ui.backwardButton.clicked.connect(self.searchPrevious)

        self.ui.lineEdit.textChanged.connect(self.onSearchTextChanged)

        self.sanitizedSearchTerm = ""

    @property
    def textChanged(self):
        return self.ui.lineEdit.textChanged

    def snapToParent(self):
        pw: QAbstractScrollArea = self.parentWidget()

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
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
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
        self.parentWidget().setFocus(Qt.FocusReason.PopupFocusReason)
        self.hide()

    def onSearchTextChanged(self, text: str):
        self.sanitizedSearchTerm = text.strip().lower()
