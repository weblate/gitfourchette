################################################################################
## Form generated from reading UI file 'identitydialog1.ui'
##
## Created by: Qt User Interface Compiler version 6.4.2
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from gitfourchette.qt import *

class Ui_IdentityDialog1(object):
    def setupUi(self, IdentityDialog1):
        if not IdentityDialog1.objectName():
            IdentityDialog1.setObjectName(u"IdentityDialog1")
        IdentityDialog1.resize(488, 439)
        self.gridLayout = QGridLayout(IdentityDialog1)
        self.gridLayout.setObjectName(u"gridLayout")
        self.horizontalSpacer = QSpacerItem(13, 13, QSizePolicy.Fixed, QSizePolicy.Minimum)

        self.gridLayout.addItem(self.horizontalSpacer, 6, 0, 1, 1)

        self.emailEdit = QLineEdit(IdentityDialog1)
        self.emailEdit.setObjectName(u"emailEdit")

        self.gridLayout.addWidget(self.emailEdit, 2, 2, 1, 1)

        self.setGlobalIdentity = QRadioButton(IdentityDialog1)
        self.setGlobalIdentity.setObjectName(u"setGlobalIdentity")
        self.setGlobalIdentity.setChecked(True)

        self.gridLayout.addWidget(self.setGlobalIdentity, 5, 0, 1, 3)

        self.nameEdit = QLineEdit(IdentityDialog1)
        self.nameEdit.setObjectName(u"nameEdit")

        self.gridLayout.addWidget(self.nameEdit, 1, 2, 1, 1)

        self.verticalSpacer_2 = QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Preferred)

        self.gridLayout.addItem(self.verticalSpacer_2, 4, 0, 1, 1)

        self.help1 = QLabel(IdentityDialog1)
        self.help1.setObjectName(u"help1")
        self.help1.setEnabled(False)
        self.help1.setWordWrap(True)

        self.gridLayout.addWidget(self.help1, 6, 1, 1, 2)

        self.label_3 = QLabel(IdentityDialog1)
        self.label_3.setObjectName(u"label_3")

        self.gridLayout.addWidget(self.label_3, 2, 0, 1, 2)

        self.label_2 = QLabel(IdentityDialog1)
        self.label_2.setObjectName(u"label_2")

        self.gridLayout.addWidget(self.label_2, 1, 0, 1, 2)

        self.verticalSpacer = QSpacerItem(20, 62, QSizePolicy.Minimum, QSizePolicy.Expanding)

        self.gridLayout.addItem(self.verticalSpacer, 0, 0, 1, 1)

        self.help2 = QLabel(IdentityDialog1)
        self.help2.setObjectName(u"help2")
        self.help2.setEnabled(False)
        self.help2.setWordWrap(True)

        self.gridLayout.addWidget(self.help2, 8, 1, 1, 2)

        self.horizontalSpacer_2 = QSpacerItem(13, 13, QSizePolicy.Fixed, QSizePolicy.Minimum)

        self.gridLayout.addItem(self.horizontalSpacer_2, 8, 0, 1, 1)

        self.setLocalIdentity = QRadioButton(IdentityDialog1)
        self.setLocalIdentity.setObjectName(u"setLocalIdentity")

        self.gridLayout.addWidget(self.setLocalIdentity, 7, 0, 1, 3)

        self.verticalSpacer_3 = QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding)

        self.gridLayout.addItem(self.verticalSpacer_3, 9, 0, 1, 1)

        self.buttonBox = QDialogButtonBox(IdentityDialog1)
        self.buttonBox.setObjectName(u"buttonBox")
        self.buttonBox.setOrientation(Qt.Horizontal)
        self.buttonBox.setStandardButtons(QDialogButtonBox.Cancel|QDialogButtonBox.Ok)

        self.gridLayout.addWidget(self.buttonBox, 10, 0, 1, 3)

        self.emailValidation = QLabel(IdentityDialog1)
        self.emailValidation.setObjectName(u"emailValidation")
        self.emailValidation.setEnabled(True)
        self.emailValidation.setText(u"VAL")

        self.gridLayout.addWidget(self.emailValidation, 2, 3, 1, 1)

        self.nameValidation = QLabel(IdentityDialog1)
        self.nameValidation.setObjectName(u"nameValidation")
        self.nameValidation.setText(u"VAL")

        self.gridLayout.addWidget(self.nameValidation, 1, 3, 1, 1)

#if QT_CONFIG(shortcut)
        self.label_3.setBuddy(self.emailEdit)
        self.label_2.setBuddy(self.nameEdit)
#endif // QT_CONFIG(shortcut)
        QWidget.setTabOrder(self.nameEdit, self.emailEdit)
        QWidget.setTabOrder(self.emailEdit, self.setGlobalIdentity)
        QWidget.setTabOrder(self.setGlobalIdentity, self.setLocalIdentity)

        self.retranslateUi(IdentityDialog1)
        self.buttonBox.accepted.connect(IdentityDialog1.accept)
        self.buttonBox.rejected.connect(IdentityDialog1.reject)

        QMetaObject.connectSlotsByName(IdentityDialog1)

    def retranslateUi(self, IdentityDialog1):
        IdentityDialog1.setWindowTitle(QCoreApplication.translate("IdentityDialog1", u"Set up your Git identity", None))
        self.setGlobalIdentity.setText(QCoreApplication.translate("IdentityDialog1", u"Set &global identity", None))
        self.help1.setText(QCoreApplication.translate("IdentityDialog1", u"Will apply to all repositories on this computer.", None))
        self.label_3.setText(QCoreApplication.translate("IdentityDialog1", u"&Email:", None))
        self.label_2.setText(QCoreApplication.translate("IdentityDialog1", u"&Name:", None))
        self.help2.setText(QCoreApplication.translate("IdentityDialog1", u"You will be prompted to set up an identity for other repositories.", None))
        self.setLocalIdentity.setText(QCoreApplication.translate("IdentityDialog1", u"Set identity for this &repository only", None))
