################################################################################
## Form generated from reading UI file 'statusform.ui'
##
## Created by: Qt User Interface Compiler version 5.15.2
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from gitfourchette.qt import *


class Ui_StatusForm(object):
    def setupUi(self, StatusForm):
        if not StatusForm.objectName():
            StatusForm.setObjectName(u"StatusForm")
        StatusForm.resize(455, 125)
        self.verticalLayout = QVBoxLayout(StatusForm)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.verticalLayout.setContentsMargins(0, 0, 0, 0)
        self.stackedWidget = QStackedWidget(StatusForm)
        self.stackedWidget.setObjectName(u"stackedWidget")
        self.progressPage = QWidget()
        self.progressPage.setObjectName(u"progressPage")
        self.verticalLayout_2 = QVBoxLayout(self.progressPage)
        self.verticalLayout_2.setObjectName(u"verticalLayout_2")
        self.linkMessage = QLabel(self.progressPage)
        self.linkMessage.setObjectName(u"linkMessage")
        self.linkMessage.setText(u"blah\n"
"blah")
        self.linkMessage.setWordWrap(True)

        self.verticalLayout_2.addWidget(self.linkMessage)

        self.progressBar = QProgressBar(self.progressPage)
        self.progressBar.setObjectName(u"progressBar")
        self.progressBar.setMinimum(0)
        self.progressBar.setMaximum(0)
        self.progressBar.setValue(0)

        self.verticalLayout_2.addWidget(self.progressBar)

        self.stackedWidget.addWidget(self.progressPage)
        self.blurbPage = QWidget()
        self.blurbPage.setObjectName(u"blurbPage")
        self.horizontalLayout_2 = QHBoxLayout(self.blurbPage)
        self.horizontalLayout_2.setObjectName(u"horizontalLayout_2")
        self.blurbLabel = QLabel(self.blurbPage)
        self.blurbLabel.setObjectName(u"blurbLabel")
        self.blurbLabel.setText(u"Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.")
        self.blurbLabel.setAlignment(Qt.AlignLeading|Qt.AlignLeft|Qt.AlignTop)
        self.blurbLabel.setWordWrap(True)
        self.blurbLabel.setTextInteractionFlags(Qt.LinksAccessibleByMouse|Qt.TextSelectableByMouse)

        self.horizontalLayout_2.addWidget(self.blurbLabel)

        self.stackedWidget.addWidget(self.blurbPage)

        self.verticalLayout.addWidget(self.stackedWidget)


        self.retranslateUi(StatusForm)

        self.stackedWidget.setCurrentIndex(0)


        QMetaObject.connectSlotsByName(StatusForm)

    def retranslateUi(self, StatusForm):
        StatusForm.setWindowTitle(QCoreApplication.translate("StatusForm", u"Form", None))
