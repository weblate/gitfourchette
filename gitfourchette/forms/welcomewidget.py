from gitfourchette.forms.ui_welcomewidget import Ui_WelcomeWidget
from gitfourchette.qt import *


class WelcomeWidget(QFrame):
    newRepo = Signal()
    openRepo = Signal()
    cloneRepo = Signal()

    def __init__(self, parent):
        super().__init__(parent)

        self.ui = Ui_WelcomeWidget()
        self.ui.setupUi(self)

        logoText = self.ui.logoLabel.text().format(app=qAppName())
        logoPixmap = QPixmap("assets:icons/gitfourchette-banner.png")
        logoPixmap.setDevicePixelRatio(4)
        self.ui.logoLabel.setText(logoText)
        self.ui.logoLabel.setPixmap(logoPixmap)

        welcomeText = self.ui.welcomeLabel.text().format(app=qAppName(), version=QApplication.applicationVersion())
        self.ui.welcomeLabel.setText(welcomeText)

        self.ui.newRepoButton.clicked.connect(self.newRepo)
        self.ui.openRepoButton.clicked.connect(self.openRepo)
        self.ui.cloneRepoButton.clicked.connect(self.cloneRepo)
