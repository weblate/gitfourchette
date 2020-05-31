from PySide2 import QtWidgets, QtGui
import sys
import signal

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    # initialize Qt before importing app modules so fonts are loaded correctly
    app = QtWidgets.QApplication(sys.argv)

    pixmap = QtGui.QPixmap("icons/gf.png")
    splash = QtWidgets.QSplashScreen(pixmap)
    splash.show()
    app.processEvents()

    import MainWindow
    window = MainWindow.MainWindow()
    window.show()

    splash.finish(window)

    window.tryLoadSession()

    app.exec_()
