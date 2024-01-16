from gitfourchette.qt import *
from gitfourchette.forms.ui_aboutdialog import Ui_AboutDialog
from gitfourchette.toolbox import *
from textwrap import dedent
import contextlib
import pygit2
import sys


WEBSITE_URL = "https://github.com/jorio/gitfourchette"
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


def simpleLink(url):
    return f"<a href='{url}'>{url}</a>"

class AboutDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)

        self.ui = Ui_AboutDialog()
        self.ui.setupUi(self)

        appVersion = QApplication.applicationVersion()
        appName = qAppName()

        self.setWindowTitle(self.windowTitle().format(appName))

        if APP_BUILD_DATE:
            buildDate = " " + self.tr("(built on {date})").format(date=APP_BUILD_DATE)
        else:
            buildDate = ""

        tagline = self.tr("The comfortable Git UI for Linux.")
        header = dedent(f"""\
            <span style="font-size: x-large"><b>{appName}</b> {appVersion}</span>{buildDate}
            <br>{tagline}
            <br>Copyright © 2024 Iliyas Jorio
            <br>{simpleLink(WEBSITE_URL)}
            """)

        blurb = paragraphs(
            self.tr("{app} is free software that I develop in my spare time."),
            self.tr("If you enjoy using it, feel free to make a donation at {donate}. "
                    "Every little bit encourages the continuation of the project!"),
            self.tr("Thank you for your support!"),
        ).format(app=appName, donate=simpleLink(DONATE_URL))

        self.ui.header.setText(header)
        self.ui.header.setOpenExternalLinks(True)

        self.ui.mugshot.setText("")
        self.ui.mugshot.setPixmap(QPixmap("assets:mug.png"))

        self.ui.aboutBlurb.setText(blurb)
        self.ui.aboutBlurb.setOpenExternalLinks(True)

        pixmap = QPixmap("assets:gitfourchette.png")
        pixmap.setDevicePixelRatio(5)
        self.ui.iconLabel.setPixmap(pixmap)

        qtBindingSuffix = ""
        if QTPY:
            from qtpy import __version__ as qtpyVersion
            qtBindingSuffix = f" (via qtpy {qtpyVersion})"

        components = dedent(f"""\
            {appName} {appVersion}{'-debug' if __debug__ else ''}
            {buildDate}
            pygit2 {pygit2.__version__}
            libgit2 {pygit2.LIBGIT2_VERSION} ({', '.join(getPygit2FeatureStrings())})
            {qtBindingName} {qtBindingVersion}{qtBindingSuffix}
            Qt {qVersion()}
            Python {'.'.join(str(i) for i in sys.version_info)}
            """)
        self.ui.componentsBlurb.setText(components)


def showAboutDialog(parent: QWidget):
    dialog = AboutDialog(parent)
    dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    dialog.show()
