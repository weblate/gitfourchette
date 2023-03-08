################################################################################
## Form generated from reading UI file 'identitydialog2.ui'
##
## Created by: Qt User Interface Compiler version 6.4.2
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from gitfourchette.qt import *

class Ui_IdentityDialog2(object):
    def setupUi(self, IdentityDialog2):
        if not IdentityDialog2.objectName():
            IdentityDialog2.setObjectName(u"IdentityDialog2")
        IdentityDialog2.resize(526, 410)
        self.gridLayout = QGridLayout(IdentityDialog2)
        self.gridLayout.setObjectName(u"gridLayout")
        self.identityGroupBox = QGroupBox(IdentityDialog2)
        self.identityGroupBox.setObjectName(u"identityGroupBox")
        self.gridLayout_2 = QGridLayout(self.identityGroupBox)
        self.gridLayout_2.setObjectName(u"gridLayout_2")
        self.label = QLabel(self.identityGroupBox)
        self.label.setObjectName(u"label")

        self.gridLayout_2.addWidget(self.label, 0, 0, 1, 1)

        self.label_2 = QLabel(self.identityGroupBox)
        self.label_2.setObjectName(u"label_2")

        self.gridLayout_2.addWidget(self.label_2, 1, 0, 1, 1)

        self.nameEdit = QLineEdit(self.identityGroupBox)
        self.nameEdit.setObjectName(u"nameEdit")

        self.gridLayout_2.addWidget(self.nameEdit, 0, 1, 1, 1)

        self.emailEdit = QLineEdit(self.identityGroupBox)
        self.emailEdit.setObjectName(u"emailEdit")

        self.gridLayout_2.addWidget(self.emailEdit, 1, 1, 1, 1)

        self.emailValidation = QLabel(self.identityGroupBox)
        self.emailValidation.setObjectName(u"emailValidation")
        self.emailValidation.setText(u"VAL")

        self.gridLayout_2.addWidget(self.emailValidation, 1, 2, 1, 1)

        self.nameValidation = QLabel(self.identityGroupBox)
        self.nameValidation.setObjectName(u"nameValidation")
        self.nameValidation.setText(u"VAL")

        self.gridLayout_2.addWidget(self.nameValidation, 0, 2, 1, 1)


        self.gridLayout.addWidget(self.identityGroupBox, 3, 0, 1, 1)

        self.verticalSpacer_3 = QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Preferred)

        self.gridLayout.addItem(self.verticalSpacer_3, 2, 0, 1, 1)

        self.localIdentityCheckBox = QCheckBox(IdentityDialog2)
        self.localIdentityCheckBox.setObjectName(u"localIdentityCheckBox")

        self.gridLayout.addWidget(self.localIdentityCheckBox, 1, 0, 1, 1)

        self.verticalSpacer_2 = QSpacerItem(20, 60, QSizePolicy.Minimum, QSizePolicy.Expanding)

        self.gridLayout.addItem(self.verticalSpacer_2, 4, 0, 1, 1)

        self.verticalSpacer = QSpacerItem(20, 61, QSizePolicy.Minimum, QSizePolicy.Expanding)

        self.gridLayout.addItem(self.verticalSpacer, 0, 0, 1, 1)

        self.buttonBox = QDialogButtonBox(IdentityDialog2)
        self.buttonBox.setObjectName(u"buttonBox")
        self.buttonBox.setOrientation(Qt.Horizontal)
        self.buttonBox.setStandardButtons(QDialogButtonBox.Cancel|QDialogButtonBox.Ok)

        self.gridLayout.addWidget(self.buttonBox, 5, 0, 1, 1)

#if QT_CONFIG(shortcut)
        self.label.setBuddy(self.nameEdit)
        self.label_2.setBuddy(self.emailEdit)
#endif // QT_CONFIG(shortcut)

        self.retranslateUi(IdentityDialog2)
        self.buttonBox.accepted.connect(IdentityDialog2.accept)
        self.buttonBox.rejected.connect(IdentityDialog2.reject)

        QMetaObject.connectSlotsByName(IdentityDialog2)

    def retranslateUi(self, IdentityDialog2):
        IdentityDialog2.setWindowTitle(QCoreApplication.translate("IdentityDialog2", u"Set up your Git identity", None))
        self.identityGroupBox.setTitle(QCoreApplication.translate("IdentityDialog2", u"Custom identity for \u201c{0}\u201d", None))
        self.label.setText(QCoreApplication.translate("IdentityDialog2", u"&Name:", None))
        self.label_2.setText(QCoreApplication.translate("IdentityDialog2", u"&Email:", None))
        self.localIdentityCheckBox.setText(QCoreApplication.translate("IdentityDialog2", u"&Use a custom identity in repository \u201c{0}\u201d", None))
