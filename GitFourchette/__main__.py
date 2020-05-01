# https://stackoverflow.com/questions/20061898/gitpython-and-git-diff
# https://www.saltycrane.com/blog/2008/01/pyqt4-qitemdelegate-example-with/

import PySide2.QtWidgets
import signal

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    # initialize Qt before importing app modules so fonts are loaded correctly
    app = PySide2.QtWidgets.QApplication([])

    import MainWindow
    window = MainWindow.MainWindow()
    window.show()

    import globals
    history = globals.getRepoHistory()
    if len(history) > 0:
        window.setRepo(history[0])

    app.exec_()
