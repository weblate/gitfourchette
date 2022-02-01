################################################################################
## Form generated from reading UI file 'remotedialog.ui'
##
## Created by: Qt User Interface Compiler version 5.15.2
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from allqt import *

class Ui_RemoteDialog(object):
    def setupUi(self, RemoteDialog):
        if not RemoteDialog.objectName():
            RemoteDialog.setObjectName(u"RemoteDialog")
        RemoteDialog.setWindowModality(Qt.NonModal)
        RemoteDialog.setEnabled(True)
        RemoteDialog.resize(594, 122)
        sizePolicy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(RemoteDialog.sizePolicy().hasHeightForWidth())
        RemoteDialog.setSizePolicy(sizePolicy)
        RemoteDialog.setSizeGripEnabled(False)
        RemoteDialog.setModal(True)
        self.formLayout = QFormLayout(RemoteDialog)
        self.formLayout.setObjectName(u"formLayout")
        self.nameLabel = QLabel(RemoteDialog)
        self.nameLabel.setObjectName(u"nameLabel")

        self.formLayout.setWidget(0, QFormLayout.LabelRole, self.nameLabel)

        self.nameEdit = QLineEdit(RemoteDialog)
        self.nameEdit.setObjectName(u"nameEdit")

        self.formLayout.setWidget(0, QFormLayout.FieldRole, self.nameEdit)

        self.urlLabel = QLabel(RemoteDialog)
        self.urlLabel.setObjectName(u"urlLabel")

        self.formLayout.setWidget(1, QFormLayout.LabelRole, self.urlLabel)

        self.urlEdit = QLineEdit(RemoteDialog)
        self.urlEdit.setObjectName(u"urlEdit")

        self.formLayout.setWidget(1, QFormLayout.FieldRole, self.urlEdit)

        self.buttonBox = QDialogButtonBox(RemoteDialog)
        self.buttonBox.setObjectName(u"buttonBox")
        self.buttonBox.setOrientation(Qt.Horizontal)
        self.buttonBox.setStandardButtons(QDialogButtonBox.Cancel|QDialogButtonBox.Ok)
        self.buttonBox.setCenterButtons(False)

        self.formLayout.setWidget(2, QFormLayout.SpanningRole, self.buttonBox)


        self.retranslateUi(RemoteDialog)
        self.buttonBox.accepted.connect(RemoteDialog.accept)
        self.buttonBox.rejected.connect(RemoteDialog.reject)

        QMetaObject.connectSlotsByName(RemoteDialog)

    def retranslateUi(self, RemoteDialog):
        RemoteDialog.setWindowTitle(QCoreApplication.translate("RemoteDialog", u"Edit remote", None))
        self.nameLabel.setText(QCoreApplication.translate("RemoteDialog", u"Name", None))
        self.urlLabel.setText(QCoreApplication.translate("RemoteDialog", u"URL", None))
