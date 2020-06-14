from PySide2 import QtWidgets, QtGui
import sys
import signal
import traceback


def excepthook(exctype, value, tb):
    # run default exception hook that we backed up earlier
    sys._excepthook(exctype, value, tb)
    QtWidgets.QMessageBox.critical(None, "Unhandled exception", F"{value.__class__.__name__}: {value}")


if __name__ == "__main__":
    # allow interrupting with Control-C
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    # inject our own exception hook to show an error dialog in case of unhandled exceptions
    sys._excepthook = sys.excepthook
    sys.excepthook = excepthook

    # initialize Qt before importing app modules so fonts are loaded correctly
    app = QtWidgets.QApplication(sys.argv)
    with open("icons/style.qss", "r") as f:
        app.setStyleSheet(f.read())

    import MainWindow
    window = MainWindow.MainWindow()
    window.show()

    try:
        window.tryLoadSession()
    except BaseException as e:
        traceback.print_exc()
        QtWidgets.QMessageBox.critical(window, "Error",
            F"Couldn't resume previous session.\n{e.__class__.__name__}: {e}.\nCheck stderr for details.")

    app.exec_()
