# Form implementation generated from reading ui file 'welcomewidget.ui'
#
# Created by: PyQt6 UI code generator 6.8.0
#
# WARNING: Any manual changes made to this file will be lost when pyuic6 is
# run again.  Do not edit this file unless you know what you are doing.


from gitfourchette.localization import *
from gitfourchette.qt import *


class Ui_WelcomeWidget(object):
    def setupUi(self, WelcomeWidget):
        WelcomeWidget.setObjectName("WelcomeWidget")
        WelcomeWidget.resize(521, 288)
        self.gridLayout = QGridLayout(WelcomeWidget)
        self.gridLayout.setObjectName("gridLayout")
        self.cloneRepoButton = QPushButton(parent=WelcomeWidget)
        self.cloneRepoButton.setObjectName("cloneRepoButton")
        self.gridLayout.addWidget(self.cloneRepoButton, 9, 1, 1, 1)
        self.newRepoButton = QPushButton(parent=WelcomeWidget)
        self.newRepoButton.setObjectName("newRepoButton")
        self.gridLayout.addWidget(self.newRepoButton, 7, 1, 1, 1)
        spacerItem = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.gridLayout.addItem(spacerItem, 8, 0, 1, 1)
        self.openRepoButton = QPushButton(parent=WelcomeWidget)
        self.openRepoButton.setObjectName("openRepoButton")
        self.gridLayout.addWidget(self.openRepoButton, 8, 1, 1, 1)
        spacerItem1 = QSpacerItem(20, 27, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        self.gridLayout.addItem(spacerItem1, 10, 1, 1, 1)
        spacerItem2 = QSpacerItem(60, 1, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.gridLayout.addItem(spacerItem2, 8, 2, 1, 1)
        self.recentReposButton = QPushButton(parent=WelcomeWidget)
        self.recentReposButton.setObjectName("recentReposButton")
        self.gridLayout.addWidget(self.recentReposButton, 5, 1, 1, 1)
        spacerItem3 = QSpacerItem(20, 27, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        self.gridLayout.addItem(spacerItem3, 0, 1, 1, 1)
        spacerItem4 = QSpacerItem(20, 27, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        self.gridLayout.addItem(spacerItem4, 4, 1, 1, 1)
        spacerItem5 = QSpacerItem(20, 20, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.gridLayout.addItem(spacerItem5, 6, 1, 1, 1)
        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setSpacing(12)
        self.horizontalLayout.setObjectName("horizontalLayout")
        spacerItem6 = QSpacerItem(40, 1, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.horizontalLayout.addItem(spacerItem6)
        self.logoLabel = QLabel(parent=WelcomeWidget)
        self.logoLabel.setText("(LOGO)")
        self.logoLabel.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignTrailing|Qt.AlignmentFlag.AlignVCenter)
        self.logoLabel.setObjectName("logoLabel")
        self.horizontalLayout.addWidget(self.logoLabel)
        self.welcomeLabel = QLabel(parent=WelcomeWidget)
        self.welcomeLabel.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.welcomeLabel.setObjectName("welcomeLabel")
        self.horizontalLayout.addWidget(self.welcomeLabel)
        spacerItem7 = QSpacerItem(40, 1, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.horizontalLayout.addItem(spacerItem7)
        self.gridLayout.addLayout(self.horizontalLayout, 1, 0, 1, 3)

        self.retranslateUi(WelcomeWidget)
        QMetaObject.connectSlotsByName(WelcomeWidget)
        WelcomeWidget.setTabOrder(self.recentReposButton, self.newRepoButton)
        WelcomeWidget.setTabOrder(self.newRepoButton, self.openRepoButton)
        WelcomeWidget.setTabOrder(self.openRepoButton, self.cloneRepoButton)

    def retranslateUi(self, WelcomeWidget):
        WelcomeWidget.setWindowTitle(_p("WelcomeWidget", "Welcome"))
        self.cloneRepoButton.setText(_p("WelcomeWidget", "Clone remote repository"))
        self.newRepoButton.setText(_p("WelcomeWidget", "New empty repository"))
        self.openRepoButton.setText(_p("WelcomeWidget", "Open local repository"))
        self.recentReposButton.setText(_p("WelcomeWidget", "Recent repositories"))
        self.welcomeLabel.setText(_p("WelcomeWidget", "Welcome to<br>{app}"))
