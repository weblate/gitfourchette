################################################################################
## Form generated from reading UI file 'pushdialog.ui'
##
## Created by: Qt User Interface Compiler version 6.4.2
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
        PushDialog.resize(570, 410)
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

        self.localBranchEdit = QComboBox(PushDialog)
        self.localBranchEdit.setObjectName(u"localBranchEdit")
        sizePolicy1 = QSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.localBranchEdit.sizePolicy().hasHeightForWidth())
        self.localBranchEdit.setSizePolicy(sizePolicy1)
        self.localBranchEdit.setInsertPolicy(QComboBox.NoInsert)

        self.formLayout.setWidget(0, QFormLayout.FieldRole, self.localBranchEdit)

        self.remoteBranchLabel = QLabel(PushDialog)
        self.remoteBranchLabel.setObjectName(u"remoteBranchLabel")

        self.formLayout.setWidget(1, QFormLayout.LabelRole, self.remoteBranchLabel)

        self.remoteBranchEdit = QComboBox(PushDialog)
        self.remoteBranchEdit.setObjectName(u"remoteBranchEdit")
        sizePolicy1.setHeightForWidth(self.remoteBranchEdit.sizePolicy().hasHeightForWidth())
        self.remoteBranchEdit.setSizePolicy(sizePolicy1)
        self.remoteBranchEdit.setInsertPolicy(QComboBox.NoInsert)
        self.remoteBranchEdit.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)

        self.formLayout.setWidget(1, QFormLayout.FieldRole, self.remoteBranchEdit)

        self.verticalSpacer = QSpacerItem(20, 8, QSizePolicy.Minimum, QSizePolicy.Preferred)

        self.formLayout.setItem(8, QFormLayout.LabelRole, self.verticalSpacer)

        self.groupBox = QGroupBox(PushDialog)
        self.groupBox.setObjectName(u"groupBox")
        sizePolicy2 = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.groupBox.sizePolicy().hasHeightForWidth())
        self.groupBox.setSizePolicy(sizePolicy2)
        self.verticalLayout = QVBoxLayout(self.groupBox)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.verticalLayout.setContentsMargins(0, 0, 0, 0)
        self.statusForm = StatusForm(self.groupBox)
        self.statusForm.setObjectName(u"statusForm")

        self.verticalLayout.addWidget(self.statusForm)


        self.formLayout.setWidget(9, QFormLayout.SpanningRole, self.groupBox)

        self.newRemoteBranchGroupBox = QGroupBox(PushDialog)
        self.newRemoteBranchGroupBox.setObjectName(u"newRemoteBranchGroupBox")
        self.newRemoteBranchGroupBox.setFlat(True)
        self.gridLayout = QGridLayout(self.newRemoteBranchGroupBox)
        self.gridLayout.setObjectName(u"gridLayout")
        self.gridLayout.setHorizontalSpacing(-1)
        self.gridLayout.setContentsMargins(0, 0, 0, 0)
        self.remoteNameLabel = QLabel(self.newRemoteBranchGroupBox)
        self.remoteNameLabel.setObjectName(u"remoteNameLabel")
        self.remoteNameLabel.setText(u"REMOTE/")

        self.gridLayout.addWidget(self.remoteNameLabel, 0, 0, 1, 1)

        self.newRemoteBranchNameEdit = QLineEdit(self.newRemoteBranchGroupBox)
        self.newRemoteBranchNameEdit.setObjectName(u"newRemoteBranchNameEdit")

        self.gridLayout.addWidget(self.newRemoteBranchNameEdit, 0, 1, 1, 1)


        self.formLayout.setWidget(2, QFormLayout.FieldRole, self.newRemoteBranchGroupBox)

        self.label = QLabel(PushDialog)
        self.label.setObjectName(u"label")

        self.formLayout.setWidget(3, QFormLayout.LabelRole, self.label)

        self.trackCheckBox = QCheckBox(PushDialog)
        self.trackCheckBox.setObjectName(u"trackCheckBox")

        self.formLayout.setWidget(3, QFormLayout.FieldRole, self.trackCheckBox)

        self.trackingLabel = QLabel(PushDialog)
        self.trackingLabel.setObjectName(u"trackingLabel")
        self.trackingLabel.setText(u"tracking text 2")
        self.trackingLabel.setTextFormat(Qt.RichText)

        self.formLayout.setWidget(4, QFormLayout.FieldRole, self.trackingLabel)

        self.forcePushCheckBox = QCheckBox(PushDialog)
        self.forcePushCheckBox.setObjectName(u"forcePushCheckBox")

        self.formLayout.setWidget(5, QFormLayout.FieldRole, self.forcePushCheckBox)

        self.label_2 = QLabel(PushDialog)
        self.label_2.setObjectName(u"label_2")

        self.formLayout.setWidget(5, QFormLayout.LabelRole, self.label_2)

        self.buttonBox = QDialogButtonBox(PushDialog)
        self.buttonBox.setObjectName(u"buttonBox")
        self.buttonBox.setOrientation(Qt.Horizontal)
        self.buttonBox.setStandardButtons(QDialogButtonBox.Cancel|QDialogButtonBox.Ok)

        self.formLayout.setWidget(19, QFormLayout.SpanningRole, self.buttonBox)

#if QT_CONFIG(shortcut)
        self.localBranchLabel.setBuddy(self.localBranchEdit)
        self.remoteBranchLabel.setBuddy(self.remoteBranchEdit)
        self.label.setBuddy(self.trackCheckBox)
        self.label_2.setBuddy(self.forcePushCheckBox)
#endif // QT_CONFIG(shortcut)
        QWidget.setTabOrder(self.localBranchEdit, self.remoteBranchEdit)
        QWidget.setTabOrder(self.remoteBranchEdit, self.newRemoteBranchNameEdit)
        QWidget.setTabOrder(self.newRemoteBranchNameEdit, self.trackCheckBox)
        QWidget.setTabOrder(self.trackCheckBox, self.forcePushCheckBox)

        self.retranslateUi(PushDialog)
        self.buttonBox.rejected.connect(PushDialog.reject)

        QMetaObject.connectSlotsByName(PushDialog)

    def retranslateUi(self, PushDialog):
        PushDialog.setWindowTitle(QCoreApplication.translate("PushDialog", u"Push branch", None))
        self.localBranchLabel.setText(QCoreApplication.translate("PushDialog", u"&Local branch", None))
        self.remoteBranchLabel.setText(QCoreApplication.translate("PushDialog", u"Push &to", None))
        self.groupBox.setTitle(QCoreApplication.translate("PushDialog", u"Status", None))
        self.newRemoteBranchGroupBox.setTitle("")
        self.newRemoteBranchNameEdit.setText("")
        self.newRemoteBranchNameEdit.setPlaceholderText(QCoreApplication.translate("PushDialog", u"Branch name on remote", None))
        self.label.setText(QCoreApplication.translate("PushDialog", u"Tracking", None))
        self.trackCheckBox.setText(QCoreApplication.translate("PushDialog", u"&Track this remote branch after pushing", None))
        self.forcePushCheckBox.setText(QCoreApplication.translate("PushDialog", u"&Force push", None))
        self.label_2.setText(QCoreApplication.translate("PushDialog", u"Force", None))
