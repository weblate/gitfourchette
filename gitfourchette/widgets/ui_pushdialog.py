################################################################################
## Form generated from reading UI file 'pushdialog.ui'
##
## Created by: Qt User Interface Compiler version 5.15.6
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from gitfourchette.qt import *

from gitfourchette.widgets.statusform import StatusForm


class Ui_PushDialog(object):
    def setupUi(self, PushDialog):
        if not PushDialog.objectName():
            PushDialog.setObjectName(u"PushDialog")
        PushDialog.setWindowModality(Qt.NonModal)
        PushDialog.setEnabled(True)
        PushDialog.resize(570, 355)
        sizePolicy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(PushDialog.sizePolicy().hasHeightForWidth())
        PushDialog.setSizePolicy(sizePolicy)
        PushDialog.setSizeGripEnabled(False)
        PushDialog.setModal(True)
        self.formLayout = QFormLayout(PushDialog)
        self.formLayout.setObjectName(u"formLayout")
        self.formLayout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        self.localBranchLabel = QLabel(PushDialog)
        self.localBranchLabel.setObjectName(u"localBranchLabel")

        self.formLayout.setWidget(0, QFormLayout.LabelRole, self.localBranchLabel)

        self.horizontalLayout_6 = QHBoxLayout()
        self.horizontalLayout_6.setObjectName(u"horizontalLayout_6")
        self.localBranchEdit = QComboBox(PushDialog)
        self.localBranchEdit.setObjectName(u"localBranchEdit")
        sizePolicy1 = QSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.localBranchEdit.sizePolicy().hasHeightForWidth())
        self.localBranchEdit.setSizePolicy(sizePolicy1)
        self.localBranchEdit.setEditable(False)
        self.localBranchEdit.setInsertPolicy(QComboBox.NoInsert)

        self.horizontalLayout_6.addWidget(self.localBranchEdit)

        self.trackingLabel = QLabel(PushDialog)
        self.trackingLabel.setObjectName(u"trackingLabel")
        self.trackingLabel.setEnabled(False)
        sizePolicy2 = QSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.trackingLabel.sizePolicy().hasHeightForWidth())
        self.trackingLabel.setSizePolicy(sizePolicy2)
        self.trackingLabel.setText(u"tracking very very long remote branch name lalala")

        self.horizontalLayout_6.addWidget(self.trackingLabel)

        self.horizontalLayout_6.setStretch(0, 3)
        self.horizontalLayout_6.setStretch(1, 2)

        self.formLayout.setLayout(0, QFormLayout.FieldRole, self.horizontalLayout_6)

        self.remoteBranchLabel = QLabel(PushDialog)
        self.remoteBranchLabel.setObjectName(u"remoteBranchLabel")

        self.formLayout.setWidget(1, QFormLayout.LabelRole, self.remoteBranchLabel)

        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.remoteBranchEdit = QComboBox(PushDialog)
        self.remoteBranchEdit.setObjectName(u"remoteBranchEdit")
        sizePolicy1.setHeightForWidth(self.remoteBranchEdit.sizePolicy().hasHeightForWidth())
        self.remoteBranchEdit.setSizePolicy(sizePolicy1)
        self.remoteBranchEdit.setInsertPolicy(QComboBox.NoInsert)
        self.remoteBranchEdit.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)

        self.horizontalLayout.addWidget(self.remoteBranchEdit)

        self.remoteBranchOptionsStack = QStackedWidget(PushDialog)
        self.remoteBranchOptionsStack.setObjectName(u"remoteBranchOptionsStack")
        sizePolicy.setHeightForWidth(self.remoteBranchOptionsStack.sizePolicy().hasHeightForWidth())
        self.remoteBranchOptionsStack.setSizePolicy(sizePolicy)
        self.forcePushPage = QWidget()
        self.forcePushPage.setObjectName(u"forcePushPage")
        self.horizontalLayout_3 = QHBoxLayout(self.forcePushPage)
        self.horizontalLayout_3.setObjectName(u"horizontalLayout_3")
        self.horizontalLayout_3.setContentsMargins(0, 0, 0, 0)
        self.remoteBranchOptionsStack.addWidget(self.forcePushPage)
        self.customRemoteBranchNamePage = QWidget()
        self.customRemoteBranchNamePage.setObjectName(u"customRemoteBranchNamePage")
        self.horizontalLayout_4 = QHBoxLayout(self.customRemoteBranchNamePage)
        self.horizontalLayout_4.setObjectName(u"horizontalLayout_4")
        self.horizontalLayout_4.setContentsMargins(0, 0, 0, 0)
        self.customRemoteBranchNameEdit = QLineEdit(self.customRemoteBranchNamePage)
        self.customRemoteBranchNameEdit.setObjectName(u"customRemoteBranchNameEdit")

        self.horizontalLayout_4.addWidget(self.customRemoteBranchNameEdit)

        self.remoteBranchOptionsStack.addWidget(self.customRemoteBranchNamePage)

        self.horizontalLayout.addWidget(self.remoteBranchOptionsStack)

        self.horizontalLayout.setStretch(0, 3)
        self.horizontalLayout.setStretch(1, 2)

        self.formLayout.setLayout(1, QFormLayout.FieldRole, self.horizontalLayout)

        self.forcePushCheckBox = QCheckBox(PushDialog)
        self.forcePushCheckBox.setObjectName(u"forcePushCheckBox")

        self.formLayout.setWidget(2, QFormLayout.FieldRole, self.forcePushCheckBox)

        self.buttonBox = QDialogButtonBox(PushDialog)
        self.buttonBox.setObjectName(u"buttonBox")
        self.buttonBox.setOrientation(Qt.Horizontal)
        self.buttonBox.setStandardButtons(QDialogButtonBox.Cancel|QDialogButtonBox.Ok)
        self.buttonBox.setCenterButtons(False)

        self.formLayout.setWidget(6, QFormLayout.FieldRole, self.buttonBox)

        self.trackCheckBox = QCheckBox(PushDialog)
        self.trackCheckBox.setObjectName(u"trackCheckBox")
        self.trackCheckBox.setText(u"Track")

        self.formLayout.setWidget(3, QFormLayout.FieldRole, self.trackCheckBox)

        self.groupBox = QGroupBox(PushDialog)
        self.groupBox.setObjectName(u"groupBox")
        sizePolicy3 = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        sizePolicy3.setHorizontalStretch(0)
        sizePolicy3.setVerticalStretch(0)
        sizePolicy3.setHeightForWidth(self.groupBox.sizePolicy().hasHeightForWidth())
        self.groupBox.setSizePolicy(sizePolicy3)
        self.verticalLayout = QVBoxLayout(self.groupBox)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.statusForm = StatusForm(self.groupBox)
        self.statusForm.setObjectName(u"statusForm")

        self.verticalLayout.addWidget(self.statusForm)


        self.formLayout.setWidget(4, QFormLayout.FieldRole, self.groupBox)

        self.statusLabel = QLabel(PushDialog)
        self.statusLabel.setObjectName(u"statusLabel")

        self.formLayout.setWidget(4, QFormLayout.LabelRole, self.statusLabel)

        self.label = QLabel(PushDialog)
        self.label.setObjectName(u"label")

        self.formLayout.setWidget(2, QFormLayout.LabelRole, self.label)

#if QT_CONFIG(shortcut)
        self.localBranchLabel.setBuddy(self.localBranchEdit)
        self.remoteBranchLabel.setBuddy(self.remoteBranchEdit)
#endif // QT_CONFIG(shortcut)
        QWidget.setTabOrder(self.localBranchEdit, self.remoteBranchEdit)
        QWidget.setTabOrder(self.remoteBranchEdit, self.customRemoteBranchNameEdit)
        QWidget.setTabOrder(self.customRemoteBranchNameEdit, self.forcePushCheckBox)

        self.retranslateUi(PushDialog)
        self.buttonBox.rejected.connect(PushDialog.reject)

        self.remoteBranchOptionsStack.setCurrentIndex(1)


        QMetaObject.connectSlotsByName(PushDialog)

    def retranslateUi(self, PushDialog):
        PushDialog.setWindowTitle(QCoreApplication.translate("PushDialog", u"Push branch", None))
        self.localBranchLabel.setText(QCoreApplication.translate("PushDialog", u"&Local branch", None))
        self.remoteBranchLabel.setText(QCoreApplication.translate("PushDialog", u"Push &to", None))
        self.customRemoteBranchNameEdit.setPlaceholderText(QCoreApplication.translate("PushDialog", u"Branch name on remote", None))
        self.forcePushCheckBox.setText(QCoreApplication.translate("PushDialog", u"&Force push", None))
        self.groupBox.setTitle("")
        self.statusLabel.setText(QCoreApplication.translate("PushDialog", u"Status", None))
        self.label.setText(QCoreApplication.translate("PushDialog", u"Options", None))
