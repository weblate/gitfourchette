################################################################################
## Form generated from reading UI file 'remotedialog.ui'
##
## Created by: Qt User Interface Compiler version 6.4.2
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from gitfourchette.qt import *

class Ui_RemoteDialog(object):
    def setupUi(self, RemoteDialog):
        if not RemoteDialog.objectName():
            RemoteDialog.setObjectName(u"RemoteDialog")
        RemoteDialog.setWindowModality(Qt.NonModal)
        RemoteDialog.setEnabled(True)
        RemoteDialog.resize(500, 296)
        sizePolicy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(RemoteDialog.sizePolicy().hasHeightForWidth())
        RemoteDialog.setSizePolicy(sizePolicy)
        RemoteDialog.setSizeGripEnabled(False)
        RemoteDialog.setModal(True)
        self.gridLayout_2 = QGridLayout(RemoteDialog)
        self.gridLayout_2.setObjectName(u"gridLayout_2")
        self.verticalSpacer = QSpacerItem(20, 20, QSizePolicy.Minimum, QSizePolicy.Fixed)

        self.gridLayout_2.addItem(self.verticalSpacer, 2, 0, 1, 1)

        self.urlLabel = QLabel(RemoteDialog)
        self.urlLabel.setObjectName(u"urlLabel")

        self.gridLayout_2.addWidget(self.urlLabel, 1, 0, 1, 1)

        self.urlEdit = QLineEdit(RemoteDialog)
        self.urlEdit.setObjectName(u"urlEdit")

        self.gridLayout_2.addWidget(self.urlEdit, 1, 1, 1, 1)

        self.nameEdit = QLineEdit(RemoteDialog)
        self.nameEdit.setObjectName(u"nameEdit")

        self.gridLayout_2.addWidget(self.nameEdit, 0, 1, 1, 1)

        self.keyFileGroupBox = QGroupBox(RemoteDialog)
        self.keyFileGroupBox.setObjectName(u"keyFileGroupBox")
        sizePolicy.setHeightForWidth(self.keyFileGroupBox.sizePolicy().hasHeightForWidth())
        self.keyFileGroupBox.setSizePolicy(sizePolicy)
        self.keyFileGroupBox.setCheckable(True)
        self.gridLayout = QGridLayout(self.keyFileGroupBox)
        self.gridLayout.setObjectName(u"gridLayout")
        self.keyFileBrowseButton = QToolButton(self.keyFileGroupBox)
        self.keyFileBrowseButton.setObjectName(u"keyFileBrowseButton")

        self.gridLayout.addWidget(self.keyFileBrowseButton, 0, 2, 1, 1)

        self.keyFileValidation = QLabel(self.keyFileGroupBox)
        self.keyFileValidation.setObjectName(u"keyFileValidation")
        self.keyFileValidation.setText(u"VAL")

        self.gridLayout.addWidget(self.keyFileValidation, 0, 1, 1, 1)

        self.keyFilePathEdit = QLineEdit(self.keyFileGroupBox)
        self.keyFilePathEdit.setObjectName(u"keyFilePathEdit")

        self.gridLayout.addWidget(self.keyFilePathEdit, 0, 0, 1, 1)


        self.gridLayout_2.addWidget(self.keyFileGroupBox, 3, 0, 1, 2)

        self.buttonBox = QDialogButtonBox(RemoteDialog)
        self.buttonBox.setObjectName(u"buttonBox")
        self.buttonBox.setOrientation(Qt.Horizontal)
        self.buttonBox.setStandardButtons(QDialogButtonBox.Cancel|QDialogButtonBox.Ok)
        self.buttonBox.setCenterButtons(False)

        self.gridLayout_2.addWidget(self.buttonBox, 5, 0, 1, 2)

        self.nameLabel = QLabel(RemoteDialog)
        self.nameLabel.setObjectName(u"nameLabel")

        self.gridLayout_2.addWidget(self.nameLabel, 0, 0, 1, 1)

        self.verticalSpacer_2 = QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding)

        self.gridLayout_2.addItem(self.verticalSpacer_2, 4, 0, 1, 1)

#if QT_CONFIG(shortcut)
        self.urlLabel.setBuddy(self.urlEdit)
        self.nameLabel.setBuddy(self.nameEdit)
#endif // QT_CONFIG(shortcut)
        QWidget.setTabOrder(self.nameEdit, self.urlEdit)
        QWidget.setTabOrder(self.urlEdit, self.keyFileGroupBox)
        QWidget.setTabOrder(self.keyFileGroupBox, self.keyFilePathEdit)
        QWidget.setTabOrder(self.keyFilePathEdit, self.keyFileBrowseButton)

        self.retranslateUi(RemoteDialog)
        self.buttonBox.accepted.connect(RemoteDialog.accept)
        self.buttonBox.rejected.connect(RemoteDialog.reject)

        QMetaObject.connectSlotsByName(RemoteDialog)

    def retranslateUi(self, RemoteDialog):
        RemoteDialog.setWindowTitle(QCoreApplication.translate("RemoteDialog", u"Edit remote", None))
        self.urlLabel.setText(QCoreApplication.translate("RemoteDialog", u"&URL:", None))
        self.keyFileGroupBox.setTitle(QCoreApplication.translate("RemoteDialog", u"Use a custom &key file to access this remote", None))
        self.keyFileBrowseButton.setText(QCoreApplication.translate("RemoteDialog", u"&Browse...", None))
        self.keyFilePathEdit.setPlaceholderText(QCoreApplication.translate("RemoteDialog", u"Path to public or private key", None))
        self.nameLabel.setText(QCoreApplication.translate("RemoteDialog", u"&Name:", None))
