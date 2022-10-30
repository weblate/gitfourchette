################################################################################
## Form generated from reading UI file 'newbranchdialog.ui'
##
## Created by: Qt User Interface Compiler version 5.15.6
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from gitfourchette.qt import *


class Ui_NewBranchDialog(object):
    def setupUi(self, NewBranchDialog):
        if not NewBranchDialog.objectName():
            NewBranchDialog.setObjectName(u"NewBranchDialog")
        NewBranchDialog.setWindowModality(Qt.NonModal)
        NewBranchDialog.setEnabled(True)
        NewBranchDialog.resize(543, 202)
        sizePolicy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(NewBranchDialog.sizePolicy().hasHeightForWidth())
        NewBranchDialog.setSizePolicy(sizePolicy)
        NewBranchDialog.setSizeGripEnabled(False)
        NewBranchDialog.setModal(True)
        self.formLayout = QFormLayout(NewBranchDialog)
        self.formLayout.setObjectName(u"formLayout")
        self.formLayout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.buttonBox = QDialogButtonBox(NewBranchDialog)
        self.buttonBox.setObjectName(u"buttonBox")
        self.buttonBox.setOrientation(Qt.Horizontal)
        self.buttonBox.setStandardButtons(QDialogButtonBox.Cancel|QDialogButtonBox.Ok)
        self.buttonBox.setCenterButtons(False)

        self.formLayout.setWidget(6, QFormLayout.FieldRole, self.buttonBox)

        self.nameLayout = QVBoxLayout()
        self.nameLayout.setSpacing(0)
        self.nameLayout.setObjectName(u"nameLayout")
        self.nameEdit = QLineEdit(NewBranchDialog)
        self.nameEdit.setObjectName(u"nameEdit")

        self.nameLayout.addWidget(self.nameEdit)

        self.nameValidationText = QLabel(NewBranchDialog)
        self.nameValidationText.setObjectName(u"nameValidationText")
        self.nameValidationText.setEnabled(False)
        self.nameValidationText.setText(u"Validation")

        self.nameLayout.addWidget(self.nameValidationText)


        self.formLayout.setLayout(0, QFormLayout.FieldRole, self.nameLayout)

        self.switchToBranchCheckBox = QCheckBox(NewBranchDialog)
        self.switchToBranchCheckBox.setObjectName(u"switchToBranchCheckBox")
        self.switchToBranchCheckBox.setChecked(True)

        self.formLayout.setWidget(2, QFormLayout.FieldRole, self.switchToBranchCheckBox)

        self.optionsLabel = QLabel(NewBranchDialog)
        self.optionsLabel.setObjectName(u"optionsLabel")

        self.formLayout.setWidget(2, QFormLayout.LabelRole, self.optionsLabel)

        self.nameLabel = QLabel(NewBranchDialog)
        self.nameLabel.setObjectName(u"nameLabel")

        self.formLayout.setWidget(0, QFormLayout.LabelRole, self.nameLabel)

        self.trackRemoteBranchLayout = QHBoxLayout()
        self.trackRemoteBranchLayout.setObjectName(u"trackRemoteBranchLayout")
        self.trackRemoteBranchCheckBox = QCheckBox(NewBranchDialog)
        self.trackRemoteBranchCheckBox.setObjectName(u"trackRemoteBranchCheckBox")
        sizePolicy1 = QSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.trackRemoteBranchCheckBox.sizePolicy().hasHeightForWidth())
        self.trackRemoteBranchCheckBox.setSizePolicy(sizePolicy1)

        self.trackRemoteBranchLayout.addWidget(self.trackRemoteBranchCheckBox)

        self.trackRemoteBranchComboBox = QComboBox(NewBranchDialog)
        self.trackRemoteBranchComboBox.setObjectName(u"trackRemoteBranchComboBox")
        sizePolicy2 = QSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.trackRemoteBranchComboBox.sizePolicy().hasHeightForWidth())
        self.trackRemoteBranchComboBox.setSizePolicy(sizePolicy2)
        self.trackRemoteBranchComboBox.setInsertPolicy(QComboBox.NoInsert)

        self.trackRemoteBranchLayout.addWidget(self.trackRemoteBranchComboBox)


        self.formLayout.setLayout(3, QFormLayout.FieldRole, self.trackRemoteBranchLayout)

#if QT_CONFIG(shortcut)
        self.nameLabel.setBuddy(self.nameEdit)
#endif // QT_CONFIG(shortcut)
        QWidget.setTabOrder(self.nameEdit, self.switchToBranchCheckBox)
        QWidget.setTabOrder(self.switchToBranchCheckBox, self.trackRemoteBranchCheckBox)
        QWidget.setTabOrder(self.trackRemoteBranchCheckBox, self.trackRemoteBranchComboBox)

        self.retranslateUi(NewBranchDialog)
        self.buttonBox.rejected.connect(NewBranchDialog.reject)
        self.buttonBox.accepted.connect(NewBranchDialog.accept)
        self.trackRemoteBranchCheckBox.toggled.connect(self.trackRemoteBranchComboBox.setEnabled)

        QMetaObject.connectSlotsByName(NewBranchDialog)

    def retranslateUi(self, NewBranchDialog):
        NewBranchDialog.setWindowTitle(QCoreApplication.translate("NewBranchDialog", u"New branch", None))
        self.switchToBranchCheckBox.setText(QCoreApplication.translate("NewBranchDialog", u"Switch to branch after creating", None))
        self.optionsLabel.setText(QCoreApplication.translate("NewBranchDialog", u"Options", None))
        self.nameLabel.setText(QCoreApplication.translate("NewBranchDialog", u"Name", None))
        self.trackRemoteBranchCheckBox.setText(QCoreApplication.translate("NewBranchDialog", u"&Track remote branch", None))
