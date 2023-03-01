from gitfourchette.qt import *


class WelcomeWidget(QFrame):
    def __init__(self, parent):
        super().__init__(parent)

        logoPixmap = QPixmap("assets:gitfourchette-banner.png")
        logoPixmap.setDevicePixelRatio(4)

        logo = QLabel()
        logo.setPixmap(logoPixmap)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)

        welcomeText = QLabel(self.tr("Welcome to {0} {1}!").format(qAppName(), QApplication.applicationVersion()))
        welcomeText.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout = QVBoxLayout()
        self.setLayout(layout)
        layout.addStretch()
        layout.addWidget(logo)
        layout.addWidget(welcomeText)
        layout.addStretch()

