from gitfourchette.qt import *
import pygit2
import sys


def showAboutDialog(parent: QWidget):
    appName = QApplication.applicationDisplayName()
    appVersion = QApplication.applicationVersion()

    aboutText = F"""\
        <span style="font-size: xx-large">
            {appName}
            <b>{appVersion}</b>
        </span>
        <p>
            The comfortable git GUI.
            <br><a href="https://github.com/jorio/gitfourchette">https://github.com/jorio/gitfourchette</a>
        </p>
        <p>
            &copy; 2020-2022 Iliyas Jorio
        </p>
        <p><small>
            libgit2         <b>{pygit2.LIBGIT2_VERSION}</b><br>
            pygit2          <b>{pygit2.__version__}</b><br>
            Qt              <b>{qVersion()}</b><br>
            {qtBindingName} <b>{qtBindingVersion}</b><br>
            Python          <b>{'.'.join(str(i) for i in sys.version_info)}</b>
        </small></p>
        <p>
            Have fun!
        </p>"""

    QMessageBox.about(parent, F"About {appName} {appVersion}", aboutText)
