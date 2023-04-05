################################################################################
## Form generated from reading UI file 'aboutdialog.ui'
##
## Created by: Qt User Interface Compiler version 6.4.2
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from gitfourchette.qt import *

class Ui_AboutDialog(object):
    def setupUi(self, AboutDialog):
        if not AboutDialog.objectName():
            AboutDialog.setObjectName(u"AboutDialog")
        AboutDialog.setWindowModality(Qt.ApplicationModal)
        AboutDialog.resize(329, 434)
        self.verticalLayout = QVBoxLayout(AboutDialog)
        self.verticalLayout.setSpacing(2)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.iconLabel = QLabel(AboutDialog)
        self.iconLabel.setObjectName(u"iconLabel")
        self.iconLabel.setText(u"ICON")
        self.iconLabel.setAlignment(Qt.AlignCenter)

        self.verticalLayout.addWidget(self.iconLabel)

        self.softwareName = QLabel(AboutDialog)
        self.softwareName.setObjectName(u"softwareName")
        self.softwareName.setText(u"<span style='font-size: 24pt'>{0} <span style='font-size: 20pt'>{1}")
        self.softwareName.setAlignment(Qt.AlignCenter)

        self.verticalLayout.addWidget(self.softwareName)

        self.label_4 = QLabel(AboutDialog)
        self.label_4.setObjectName(u"label_4")
        self.label_4.setAlignment(Qt.AlignCenter)

        self.verticalLayout.addWidget(self.label_4)

        self.label_5 = QLabel(AboutDialog)
        self.label_5.setObjectName(u"label_5")
        self.label_5.setText(u"Copyright \u00a9 2023 Iliyas Jorio")
        self.label_5.setAlignment(Qt.AlignCenter)

        self.verticalLayout.addWidget(self.label_5)

        self.label_3 = QLabel(AboutDialog)
        self.label_3.setObjectName(u"label_3")
        self.label_3.setText(u"<a href=\"https://github.com/jorio/gitfourchette\">https://github.com/jorio/gitfourchette</a>")
        self.label_3.setAlignment(Qt.AlignCenter)
        self.label_3.setOpenExternalLinks(True)

        self.verticalLayout.addWidget(self.label_3)

        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.horizontalSpacer = QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)

        self.horizontalLayout.addItem(self.horizontalSpacer)

        self.donateButton = QPushButton(AboutDialog)
        self.donateButton.setObjectName(u"donateButton")
        sizePolicy = QSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.donateButton.sizePolicy().hasHeightForWidth())
        self.donateButton.setSizePolicy(sizePolicy)
        self.donateButton.setCursor(QCursor(Qt.PointingHandCursor))
        self.donateButton.setFlat(True)

        self.horizontalLayout.addWidget(self.donateButton)

        self.horizontalSpacer_2 = QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)

        self.horizontalLayout.addItem(self.horizontalSpacer_2)


        self.verticalLayout.addLayout(self.horizontalLayout)

        self.verticalSpacer = QSpacerItem(20, 16, QSizePolicy.Minimum, QSizePolicy.Fixed)

        self.verticalLayout.addItem(self.verticalSpacer)

        self.plainTextEdit = QPlainTextEdit(AboutDialog)
        self.plainTextEdit.setObjectName(u"plainTextEdit")
        self.plainTextEdit.setTabChangesFocus(True)
        self.plainTextEdit.setReadOnly(True)
        self.plainTextEdit.setPlainText(u"")

        self.verticalLayout.addWidget(self.plainTextEdit)

        self.buttonBox = QDialogButtonBox(AboutDialog)
        self.buttonBox.setObjectName(u"buttonBox")
        self.buttonBox.setStandardButtons(QDialogButtonBox.Ok)

        self.verticalLayout.addWidget(self.buttonBox)


        self.retranslateUi(AboutDialog)
        self.buttonBox.accepted.connect(AboutDialog.close)

        QMetaObject.connectSlotsByName(AboutDialog)

    def retranslateUi(self, AboutDialog):
        AboutDialog.setWindowTitle(QCoreApplication.translate("AboutDialog", u"About {0}", None))
        self.label_4.setText(QCoreApplication.translate("AboutDialog", u"The comfy Git UI for Linux.", None))
        self.donateButton.setText(QCoreApplication.translate("AboutDialog", u"Donate", None))
