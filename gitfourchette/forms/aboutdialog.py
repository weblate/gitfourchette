# -----------------------------------------------------------------------------
# Copyright (C) 2024 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

import sys
from textwrap import dedent

import pygit2

from gitfourchette.forms.ui_aboutdialog import Ui_AboutDialog
from gitfourchette.qt import *
from gitfourchette.toolbox import *

WEBSITE_URL = "https://github.com/jorio/gitfourchette"
DONATE_URL = "https://ko-fi.com/jorio"


def getPygit2FeatureStrings():
    return [f.name.lower() for f in pygit2.enums.Feature if f & pygit2.features]


def simpleLink(url):
    return f"<a href='{url}'>{url}</a>"


class AboutDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)

        self.ui = Ui_AboutDialog()
        self.ui.setupUi(self)

        appVersion = QApplication.applicationVersion()
        appName = qAppName()

        if APP_FREEZE_COMMIT:
            appVersion += f" ({APP_FREEZE_COMMIT[:7]})"

        self.setWindowTitle(self.windowTitle().format(appName))

        if APP_FREEZE_DATE:
            buildDate = f" ({APP_FREEZE_DATE})"
        else:
            buildDate = ""

        tagline = tr("The comfortable Git UI for Linux.")
        header = dedent(f"""\
            <span style="font-size: x-large"><b>{appName}</b></span>
            <br>{tagline}
            <br>{simpleLink(WEBSITE_URL)}""")
        versionText = dedent(f"""\
            <span style='color:{mutedTextColorHex(self)}'><b>Version {appVersion}</b>{buildDate}
            <br>Copyright © 2024 Iliyas Jorio""")

        blurb = paragraphs(
            self.tr("{app} is free software that I develop in my spare time."),
            self.tr("If you enjoy using it, feel free to make a donation at {donate}. "
                    "Every little bit encourages the continuation of the project!"),
            self.tr("Thank you for your support!"),
        ).format(app=appName, donate=simpleLink(DONATE_URL))

        self.ui.header.setText(header)
        self.ui.header.setOpenExternalLinks(True)

        self.ui.versionLabel.setText(versionText)

        self.ui.mugshot.setText("")
        self.ui.mugshot.setPixmap(QPixmap("assets:icons/mug"))

        self.ui.aboutBlurb.setText(blurb)
        self.ui.aboutBlurb.setOpenExternalLinks(True)

        pixmap = QPixmap("assets:icons/gitfourchette")
        pixmap.setDevicePixelRatio(4)
        self.ui.iconLabel.setPixmap(pixmap)

        qtBindingSuffix = ""

        poweredByTitle = self.tr("Powered by:")
        thirdPartyCreditsTitle = self.tr("Third-party credits:")

        components = dedent(f"""<html>\
            {appName} {appVersion}
            {buildDate}
            <br>{poweredByTitle}
            <ul style='margin: 0'>
            <li><b>pygit2</b> {pygit2.__version__}
            <li><b>libgit2</b> {pygit2.LIBGIT2_VERSION} <small>({', '.join(getPygit2FeatureStrings())})</small>
            <li><b>{QT_BINDING}</b> {QT_BINDING_VERSION}{qtBindingSuffix}
            <li><b>Qt</b> {qVersion()}
            <li><b>Python</b> {'.'.join(str(i) for i in sys.version_info)}
            </ul>

            <hr>
            {thirdPartyCreditsTitle}<br>
            <small>
            <a href='https://github.com/z3ntu/QtWaitingSpinner'>QtWaitingSpinner</a>
            (used under <a href='https://github.com/z3ntu/QtWaitingSpinner/blob/055517b18fe764c24ca4809d4a5de95c9febfceb/LICENSE.md'>MIT license</a>):
            Copyright © 2012-2014 Alexander Turkin, © 2014 William Hallatt, © 2015 Jacob Dawid, © 2016 Luca Weiss.
            </small>
            """)
        self.ui.componentsBlurb.setText(components)


def showAboutDialog(parent: QWidget):
    dialog = AboutDialog(parent)
    dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    dialog.show()
