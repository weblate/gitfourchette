from PySide2.QtWidgets import QApplication
from PySide2.QtCore import Qt
import sys
import signal
from util import excMessageBox


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
    app.setAttribute(Qt.AA_DisableWindowContextHelpButton)

    import settings
    if settings.prefs.qtStyle:
        app.setStyle(settings.prefs.qtStyle)

    import MainWindow
    window = MainWindow.MainWindow()
    window.show()

    try:
        window.tryLoadSession()
    except BaseException as e:
        excMessageBox(e, "Resume Session", "Failed to resume previous session.")

    app.exec_()
