################################################################################
## Form generated from reading UI file 'signatureform.ui'
##
## Created by: Qt User Interface Compiler version 5.15.2
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from gitfourchette.qt import *


class Ui_SignatureForm(object):
    def setupUi(self, SignatureForm):
        if not SignatureForm.objectName():
            SignatureForm.setObjectName(u"SignatureForm")
        SignatureForm.resize(311, 213)
        self.formLayout = QFormLayout(SignatureForm)
        self.formLayout.setObjectName(u"formLayout")
        self.formLayout.setContentsMargins(0, 0, 0, 0)
        self.nameLabel = QLabel(SignatureForm)
        self.nameLabel.setObjectName(u"nameLabel")

        self.formLayout.setWidget(0, QFormLayout.LabelRole, self.nameLabel)

        self.nameEdit = QLineEdit(SignatureForm)
        self.nameEdit.setObjectName(u"nameEdit")

        self.formLayout.setWidget(0, QFormLayout.FieldRole, self.nameEdit)

        self.emailLabel = QLabel(SignatureForm)
        self.emailLabel.setObjectName(u"emailLabel")

        self.formLayout.setWidget(1, QFormLayout.LabelRole, self.emailLabel)

        self.emailEdit = QLineEdit(SignatureForm)
        self.emailEdit.setObjectName(u"emailEdit")

        self.formLayout.setWidget(1, QFormLayout.FieldRole, self.emailEdit)

        self.timeLabel = QLabel(SignatureForm)
        self.timeLabel.setObjectName(u"timeLabel")

        self.formLayout.setWidget(2, QFormLayout.LabelRole, self.timeLabel)

        self.timeEdit = QDateTimeEdit(SignatureForm)
        self.timeEdit.setObjectName(u"timeEdit")
        self.timeEdit.setCurrentSection(QDateTimeEdit.YearSection)
        self.timeEdit.setDisplayFormat(u"yyyy-MM-dd HH:mm:ss (t)")
        self.timeEdit.setCalendarPopup(True)
        self.timeEdit.setTimeSpec(Qt.LocalTime)

        self.formLayout.setWidget(2, QFormLayout.FieldRole, self.timeEdit)


        self.retranslateUi(SignatureForm)

        QMetaObject.connectSlotsByName(SignatureForm)

    def retranslateUi(self, SignatureForm):
        SignatureForm.setWindowTitle(QCoreApplication.translate("SignatureForm", u"Form", None))
        self.nameLabel.setText(QCoreApplication.translate("SignatureForm", u"Name", None))
        self.emailLabel.setText(QCoreApplication.translate("SignatureForm", u"Email", None))
        self.timeLabel.setText(QCoreApplication.translate("SignatureForm", u"Time", None))
