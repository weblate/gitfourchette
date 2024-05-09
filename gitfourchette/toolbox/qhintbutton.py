from gitfourchette.qt import *
from gitfourchette.toolbox import stockIcon


class QHintButton(QToolButton):
    def __init__(self, parent=None, toolTip="", iconKey="hint"):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAutoRaise(True)
        self.setText("\u24D8")  # circled 'i'
        self.setIcon(stockIcon(iconKey))
        self.setToolTip(toolTip)
        self.setCursor(Qt.CursorShape.WhatsThisCursor)
        self.clicked[bool].connect(lambda _: QToolTip.showText(QCursor.pos(), self.toolTip(), self))  # [bool]: for PySide <6.7.0 (PYSIDE-2524)
