from dataclasses import dataclass
from gitfourchette.qt import *
from gitfourchette.util import stockIcon
from typing import Callable, Iterable, Optional
import contextlib


class ValidatorMultiplexer(QObject):
    """
    Provides input validation in multiple QLineEdits and manages the enabled
    state of a set of so-called "gated widgets" depending on the validity of
    the inputs.

    Each QLineEdit is associated to a separate validator function that takes an
    input string (the contents of the QLineEdit) and returns an error string.
    If the validator function returns an empty error string, the QLineEdit is
    deemed to have valid input.

    When the input in a QLineEdit is invalid, all gated widgets are disabled.
    The user can continue entering text into the QLineEdit, but a warning icon
    will appear in it, along with a tooltip reporting the error returned by the
    validator function.

    The gated widgets are enabled only if all QLineEdits contain valid input.

    A typical use case of this class is to disable the OK button in a QDialog
    until all QLineEdits in it are valid.
    """

    @dataclass
    class Input:
        edit: QLineEdit
        validate: Callable[[str], str]
        showWarning: bool
        inEditIcon: Optional[QAction] = None

    gatedWidgets: list[QWidget]
    inputs: list[Input]
    timer: QTimer

    def __init__(self, parent):
        super().__init__(parent)
        self.gatedWidgets = []
        self.inputs = []
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(500)

    def setGatedWidgets(self, *args: QWidget):
        self.gatedWidgets = list(args)

    def connectInput(self, edit: QLineEdit, validate: Callable[[str], str], showWarning: bool = True):
        assert isinstance(edit, QLineEdit)
        assert isinstance(validate, Callable)
        newInput = ValidatorMultiplexer.Input(edit, validate, showWarning)
        self.inputs.append(newInput)
        edit.textChanged.connect(self.run)

    def run(self):
        # Run validator on inputs
        errors: list[str] = []
        for input in self.inputs:
            if not input.edit.isVisibleTo(self.parent()) or not input.edit.isEnabledTo(self.parent()):
                # Don't validate disabled/hidden inputs
                errors.append("")
            else:
                errors.append(input.validate(input.edit.text()))

        success = all(not e for e in errors)

        # Enable/disable gated widgets
        for w in self.gatedWidgets:
            w.setEnabled(success)

        # Disable error tooltip on success
        if success:
            with contextlib.suppress(BaseException):
                self.timer.timeout.disconnect()
            self.timer.stop()
            QToolTip.hideText()

        # Set validation feedback
        for input, err in zip(self.inputs, errors):
            if not input.showWarning:
                continue

            if err:
                if not input.inEditIcon:
                    input.inEditIcon = input.edit.addAction(
                        stockIcon(QStyle.StandardPixmap.SP_MessageBoxWarning) if MACOS or WINDOWS else QIcon("assets:achtung.svg"),
                        QLineEdit.ActionPosition.TrailingPosition)

                input.inEditIcon.setToolTip(err)

                if input.edit.hasFocus():
                    with contextlib.suppress(BaseException):
                        self.timer.timeout.disconnect()
                    self.timer.stop()
                    self.timer.timeout.connect(
                        lambda t=input, err=err: QToolTip.showText(t.edit.mapToGlobal(QPoint(0, 0)), err, t.edit))
                    self.timer.start()

            elif not err and input.inEditIcon:
                input.edit.removeAction(input.inEditIcon)
                input.inEditIcon.deleteLater()
                input.inEditIcon = None
