################################################################################
## Form generated from reading UI file 'newbranchdialog.ui'
##
## Created by: Qt User Interface Compiler version 6.4.2
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
        self.nameLabel = QLabel(NewBranchDialog)
        self.nameLabel.setObjectName(u"nameLabel")

        self.formLayout.setWidget(0, QFormLayout.LabelRole, self.nameLabel)

        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.nameEdit = QLineEdit(NewBranchDialog)
        self.nameEdit.setObjectName(u"nameEdit")

        self.horizontalLayout.addWidget(self.nameEdit)

        self.nameValidation = QLabel(NewBranchDialog)
        self.nameValidation.setObjectName(u"nameValidation")
        self.nameValidation.setText(u"VAL")

        self.horizontalLayout.addWidget(self.nameValidation)


        self.formLayout.setLayout(0, QFormLayout.FieldRole, self.horizontalLayout)

        self.optionsLabel = QLabel(NewBranchDialog)
        self.optionsLabel.setObjectName(u"optionsLabel")

        self.formLayout.setWidget(2, QFormLayout.LabelRole, self.optionsLabel)

        self.switchToBranchCheckBox = QCheckBox(NewBranchDialog)
        self.switchToBranchCheckBox.setObjectName(u"switchToBranchCheckBox")
        self.switchToBranchCheckBox.setChecked(True)

        self.formLayout.setWidget(2, QFormLayout.FieldRole, self.switchToBranchCheckBox)

        self.buttonBox = QDialogButtonBox(NewBranchDialog)
        self.buttonBox.setObjectName(u"buttonBox")
        self.buttonBox.setOrientation(Qt.Horizontal)
        self.buttonBox.setStandardButtons(QDialogButtonBox.Cancel|QDialogButtonBox.Ok)
        self.buttonBox.setCenterButtons(False)

        self.formLayout.setWidget(6, QFormLayout.FieldRole, self.buttonBox)

        self.upstreamLayout = QHBoxLayout()
        self.upstreamLayout.setObjectName(u"upstreamLayout")
        self.upstreamCheckBox = QCheckBox(NewBranchDialog)
        self.upstreamCheckBox.setObjectName(u"upstreamCheckBox")
        sizePolicy1 = QSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.upstreamCheckBox.sizePolicy().hasHeightForWidth())
        self.upstreamCheckBox.setSizePolicy(sizePolicy1)

        self.upstreamLayout.addWidget(self.upstreamCheckBox)

        self.upstreamComboBox = QComboBox(NewBranchDialog)
        self.upstreamComboBox.setObjectName(u"upstreamComboBox")
        sizePolicy2 = QSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.upstreamComboBox.sizePolicy().hasHeightForWidth())
        self.upstreamComboBox.setSizePolicy(sizePolicy2)
        self.upstreamComboBox.setInsertPolicy(QComboBox.NoInsert)

        self.upstreamLayout.addWidget(self.upstreamComboBox)


        self.formLayout.setLayout(3, QFormLayout.FieldRole, self.upstreamLayout)

#if QT_CONFIG(shortcut)
        self.nameLabel.setBuddy(self.nameEdit)
#endif // QT_CONFIG(shortcut)
        QWidget.setTabOrder(self.nameEdit, self.switchToBranchCheckBox)
        QWidget.setTabOrder(self.switchToBranchCheckBox, self.upstreamCheckBox)
        QWidget.setTabOrder(self.upstreamCheckBox, self.upstreamComboBox)

        self.retranslateUi(NewBranchDialog)
        self.buttonBox.rejected.connect(NewBranchDialog.reject)
        self.buttonBox.accepted.connect(NewBranchDialog.accept)
        self.upstreamCheckBox.toggled.connect(self.upstreamComboBox.setEnabled)

        QMetaObject.connectSlotsByName(NewBranchDialog)

    def retranslateUi(self, NewBranchDialog):
        NewBranchDialog.setWindowTitle(QCoreApplication.translate("NewBranchDialog", u"New branch", None))
        self.nameLabel.setText(QCoreApplication.translate("NewBranchDialog", u"Name", None))
        self.optionsLabel.setText(QCoreApplication.translate("NewBranchDialog", u"Options", None))
        self.switchToBranchCheckBox.setText(QCoreApplication.translate("NewBranchDialog", u"Switch to branch after creating", None))
        self.upstreamCheckBox.setText(QCoreApplication.translate("NewBranchDialog", u"&Track remote branch", None))
