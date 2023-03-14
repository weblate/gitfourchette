from gitfourchette.qt import *
from gitfourchette import util
from gitfourchette.widgets.ui_aboutdialog import Ui_AboutDialog
import contextlib
import pygit2
import sys


DONATE_URL = "https://ko-fi.com/jorio"


def getPygit2FeatureStrings():
    featureNames = {
        pygit2.GIT_FEATURE_SSH: "ssh",
        pygit2.GIT_FEATURE_HTTPS: "https",
        pygit2.GIT_FEATURE_THREADS: "threads"
    }
    featureList = []
    for mask, name in featureNames.items():
        if pygit2.features & mask:
            featureList.append(name)
    return featureList


class AboutDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)

        self.ui = Ui_AboutDialog()
        self.ui.setupUi(self)

        appVersion = QApplication.applicationVersion()
        appName = qAppName()

        self.setWindowTitle(self.windowTitle().format(appName))

        self.ui.softwareName.setText(self.ui.softwareName.text().format(appName, appVersion))

        pixmap = QPixmap("assets:gitfourchette.png")
        pixmap.setDevicePixelRatio(4)
        self.ui.iconLabel.setPixmap(pixmap)

        pixmap = QPixmap("assets:kofi.png")
        self.ui.donateButton.setIcon(QIcon(pixmap))
        self.ui.donateButton.setIconSize(QSize(pixmap.width()//3, pixmap.height()//3))
        self.ui.donateButton.setText("")

        self.ui.donateButton.clicked.connect(lambda: QDesktopServices.openUrl(DONATE_URL))
        self.ui.donateButton.setToolTip(DONATE_URL)

        buildDate = ""
        if PYINSTALLER_BUNDLE:
            with contextlib.suppress(ImportError):
                import gitfourchette._buildconstants
                buildDate = (" " + self.tr("built on:", "when the software was built") +
                             " " + gitfourchette._buildconstants.buildDate)

        util.tweakWidgetFont(self.ui.plainTextEdit, 90)

        self.ui.plainTextEdit.setPlainText(F"""\
{appName} {appVersion}{'-debug' if __debug__ else ''}
{buildDate}
libgit2 {pygit2.LIBGIT2_VERSION} ({', '.join(getPygit2FeatureStrings())}) / pygit2 {pygit2.__version__}
Qt {qVersion()} / {qtBindingName} {qtBindingVersion}
Python {'.'.join(str(i) for i in sys.version_info)}""")


def showAboutDialog(parent: QWidget):
    dialog = AboutDialog(parent)
    dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    dialog.show()
