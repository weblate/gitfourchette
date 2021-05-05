from PySide6.QtCore import QSysInfo
from PySide6.QtWidgets import QApplication
from util import excMessageBox
import signal
import sys


def excepthook(exctype, value, tb):
    sys._excepthook(exctype, value, tb)
    # todo: this is not thread safe!
    excMessageBox(value)


if __name__ == "__main__":
    # allow interrupting with Control-C
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    # inject our own exception hook to show an error dialog in case of unhandled exceptions
    sys._excepthook = sys.excepthook
    sys.excepthook = excepthook

    # initialize Qt before importing app modules so fonts are loaded correctly
    app = QApplication(sys.argv)
    with open("icons/style.qss", "r") as f:
        app.setStyleSheet(f.read())

    # Hack so we don't get out-of-place Tahoma on Windows.
    # TODO: Check whether Qt 6 has made this unnecessary (when it comes out).
    if QSysInfo.productType() == "windows":
        # Get QMenu's font (which is correct) instead of using raw Segoe UI,
        # because some locales might use a different font than Segoe.
        sysFont = QApplication.font("QMenu")
        QApplication.setFont(sysFont)

    import settings

    if settings.prefs.qtStyle:
        app.setStyle(settings.prefs.qtStyle)

    import mainwindow

    window = mainwindow.MainWindow()
    window.show()
    window.tryLoadSession()
    app.exec_()
