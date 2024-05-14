import logging
import signal
import sys

from gitfourchette.qt import *


def excepthook(exctype, value, tb):
    sys.__excepthook__(exctype, value, tb)  # run default excepthook

    from gitfourchette.toolbox import excMessageBox
    excMessageBox(value, printExc=False)


def main():
    logging.basicConfig(
        stream=sys.stdout,
        level=logging.DEBUG,
        format='%(levelname).1s %(asctime)s %(filename)-16s | %(message)s',
        datefmt="%H:%M:%S")

    # inject our own exception hook to show an error dialog in case of unhandled exceptions
    # (note that this may get overridden when running under a debugger)
    sys.excepthook = excepthook

    # Initialize the application
    from gitfourchette.application import GFApplication
    app = GFApplication(sys.argv, __file__)

    # Quit app cleanly on Ctrl+C (all repos and associated file handles will be freed)
    signal.signal(signal.SIGINT, lambda *args: app.quit())

    # Force Python interpreter to run every now and then so it can run the Ctrl+C signal handler
    # (Otherwise the app won't actually die until the window regains focus, see https://stackoverflow.com/q/4938723)
    if __debug__:
        timer = QTimer()
        timer.start(300)
        timer.timeout.connect(lambda: None)

    app.beginSession()

    # Keep the app running
    app.exec()


if __name__ == "__main__":
    main()
