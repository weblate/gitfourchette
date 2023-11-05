################################################################################
## Form generated from reading UI file 'checkoutcommitdialog.ui'
##
## Created by: Qt User Interface Compiler version 6.4.2
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from gitfourchette.qt import *

class Ui_CheckoutCommitDialog(object):
    def setupUi(self, CheckoutCommitDialog):
        if not CheckoutCommitDialog.objectName():
            CheckoutCommitDialog.setObjectName(u"CheckoutCommitDialog")
        CheckoutCommitDialog.setWindowModality(Qt.NonModal)
        CheckoutCommitDialog.setEnabled(True)
        CheckoutCommitDialog.resize(581, 161)
        sizePolicy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(CheckoutCommitDialog.sizePolicy().hasHeightForWidth())
        CheckoutCommitDialog.setSizePolicy(sizePolicy)
        CheckoutCommitDialog.setSizeGripEnabled(False)
        CheckoutCommitDialog.setModal(True)
        self.verticalLayout = QVBoxLayout(CheckoutCommitDialog)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.label = QLabel(CheckoutCommitDialog)
        self.label.setObjectName(u"label")

        self.verticalLayout.addWidget(self.label)

        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.horizontalLayout.setSizeConstraint(QLayout.SetDefaultConstraint)
        self.switchToLocalBranchRadioButton = QRadioButton(CheckoutCommitDialog)
        self.switchToLocalBranchRadioButton.setObjectName(u"switchToLocalBranchRadioButton")

        self.horizontalLayout.addWidget(self.switchToLocalBranchRadioButton)

        self.switchToLocalBranchComboBox = QComboBox(CheckoutCommitDialog)
        self.switchToLocalBranchComboBox.setObjectName(u"switchToLocalBranchComboBox")

        self.horizontalLayout.addWidget(self.switchToLocalBranchComboBox)


        self.verticalLayout.addLayout(self.horizontalLayout)

        self.detachedHeadRadioButton = QRadioButton(CheckoutCommitDialog)
        self.detachedHeadRadioButton.setObjectName(u"detachedHeadRadioButton")

        self.verticalLayout.addWidget(self.detachedHeadRadioButton)

        self.createBranchRadioButton = QRadioButton(CheckoutCommitDialog)
        self.createBranchRadioButton.setObjectName(u"createBranchRadioButton")

        self.verticalLayout.addWidget(self.createBranchRadioButton)

        self.buttonBox = QDialogButtonBox(CheckoutCommitDialog)
        self.buttonBox.setObjectName(u"buttonBox")
        self.buttonBox.setOrientation(Qt.Horizontal)
        self.buttonBox.setStandardButtons(QDialogButtonBox.Cancel|QDialogButtonBox.Ok)
        self.buttonBox.setCenterButtons(False)

        self.verticalLayout.addWidget(self.buttonBox)


        self.retranslateUi(CheckoutCommitDialog)
        self.buttonBox.rejected.connect(CheckoutCommitDialog.reject)
        self.buttonBox.accepted.connect(CheckoutCommitDialog.accept)
        self.switchToLocalBranchRadioButton.toggled.connect(self.switchToLocalBranchComboBox.setEnabled)

        QMetaObject.connectSlotsByName(CheckoutCommitDialog)

    def retranslateUi(self, CheckoutCommitDialog):
        CheckoutCommitDialog.setWindowTitle(QCoreApplication.translate("CheckoutCommitDialog", u"Check out commit", None))
        self.label.setText(QCoreApplication.translate("CheckoutCommitDialog", u"How do you want to check out this commit?", None))
        self.switchToLocalBranchRadioButton.setText(QCoreApplication.translate("CheckoutCommitDialog", u"Switch to a &branch that points here:", None))
        self.detachedHeadRadioButton.setText(QCoreApplication.translate("CheckoutCommitDialog", u"Enter &detached HEAD here", None))
        self.createBranchRadioButton.setText(QCoreApplication.translate("CheckoutCommitDialog", u"Start &new branch here...", None))
