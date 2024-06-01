from gitfourchette.forms.ui_welcomewidget import Ui_WelcomeWidget
from gitfourchette.qt import *
from gitfourchette.toolbox import *


class WelcomeWidget(QFrame):
    newRepo = Signal()
    openRepo = Signal()
    cloneRepo = Signal()

    def __init__(self, parent):
        super().__init__(parent)

        self.ui = Ui_WelcomeWidget()
        self.ui.setupUi(self)

        logoPixmap = QPixmap("assets:icons/gitfourchette")
        logoPixmap.setDevicePixelRatio(4)
        self.ui.logoLabel.setText(qAppName())
        self.ui.logoLabel.setPixmap(logoPixmap)

        defaultFont = self.ui.welcomeLabel.font()
        fs1 = int(defaultFont.pointSizeF() * 1.3)
        fs2 = int(defaultFont.pointSizeF() * 1.8)
        appText = f"<span style='font-weight: bold; color: #407cbf; font-size: {fs2}pt'>{qAppName()}</span>"
        welcomeText = self.ui.welcomeLabel.text()
        welcomeText = f"<html style='font-size: {fs1}pt;'>" + welcomeText.format(app=appText)
        self.ui.welcomeLabel.setText(welcomeText)

        self.ui.newRepoButton.clicked.connect(self.newRepo)
        self.ui.openRepoButton.clicked.connect(self.openRepo)
        self.ui.cloneRepoButton.clicked.connect(self.cloneRepo)
