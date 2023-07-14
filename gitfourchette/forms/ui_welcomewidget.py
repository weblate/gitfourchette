################################################################################
## Form generated from reading UI file 'welcomewidget.ui'
##
## Created by: Qt User Interface Compiler version 6.4.3
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from gitfourchette.qt import *

class Ui_WelcomeWidget(object):
    def setupUi(self, WelcomeWidget):
        if not WelcomeWidget.objectName():
            WelcomeWidget.setObjectName(u"WelcomeWidget")
        WelcomeWidget.resize(521, 288)
        self.gridLayout = QGridLayout(WelcomeWidget)
        self.gridLayout.setObjectName(u"gridLayout")
        self.verticalSpacer = QSpacerItem(20, 27, QSizePolicy.Minimum, QSizePolicy.Expanding)

        self.gridLayout.addItem(self.verticalSpacer, 0, 1, 1, 1)

        self.horizontalSpacer = QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)

        self.gridLayout.addItem(self.horizontalSpacer, 5, 0, 1, 1)

        self.cloneRepoButton = QPushButton(WelcomeWidget)
        self.cloneRepoButton.setObjectName(u"cloneRepoButton")

        self.gridLayout.addWidget(self.cloneRepoButton, 6, 1, 1, 1)

        self.newRepoButton = QPushButton(WelcomeWidget)
        self.newRepoButton.setObjectName(u"newRepoButton")

        self.gridLayout.addWidget(self.newRepoButton, 4, 1, 1, 1)

        self.openRepoButton = QPushButton(WelcomeWidget)
        self.openRepoButton.setObjectName(u"openRepoButton")

        self.gridLayout.addWidget(self.openRepoButton, 5, 1, 1, 1)

        self.verticalSpacer_3 = QSpacerItem(20, 27, QSizePolicy.Minimum, QSizePolicy.Expanding)

        self.gridLayout.addItem(self.verticalSpacer_3, 3, 1, 1, 1)

        self.verticalSpacer_2 = QSpacerItem(20, 27, QSizePolicy.Minimum, QSizePolicy.Expanding)

        self.gridLayout.addItem(self.verticalSpacer_2, 7, 1, 1, 1)

        self.horizontalSpacer_2 = QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)

        self.gridLayout.addItem(self.horizontalSpacer_2, 5, 2, 1, 1)

        self.welcomeLabel = QLabel(WelcomeWidget)
        self.welcomeLabel.setObjectName(u"welcomeLabel")
        self.welcomeLabel.setAlignment(Qt.AlignCenter)

        self.gridLayout.addWidget(self.welcomeLabel, 2, 0, 1, 3)

        self.logoLabel = QLabel(WelcomeWidget)
        self.logoLabel.setObjectName(u"logoLabel")
        self.logoLabel.setText(u"{app}")
        self.logoLabel.setAlignment(Qt.AlignCenter)

        self.gridLayout.addWidget(self.logoLabel, 1, 0, 1, 3)


        self.retranslateUi(WelcomeWidget)

        QMetaObject.connectSlotsByName(WelcomeWidget)

    def retranslateUi(self, WelcomeWidget):
        WelcomeWidget.setWindowTitle(QCoreApplication.translate("WelcomeWidget", u"Welcome", None))
        self.cloneRepoButton.setText(QCoreApplication.translate("WelcomeWidget", u"Clone remote repository", None))
        self.newRepoButton.setText(QCoreApplication.translate("WelcomeWidget", u"New empty repository", None))
        self.openRepoButton.setText(QCoreApplication.translate("WelcomeWidget", u"Open local repository", None))
        self.welcomeLabel.setText(QCoreApplication.translate("WelcomeWidget", u"Welcome to {app} {version}!", None))
