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
        PushDialog.resize(512, 462)
        PushDialog.setSizeGripEnabled(False)
        PushDialog.setModal(True)
        self.formLayout = QFormLayout(PushDialog)
        self.formLayout.setObjectName(u"formLayout")
        self.formLayout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.localBranchLabel = QLabel(PushDialog)
        self.localBranchLabel.setObjectName(u"localBranchLabel")

        self.formLayout.setWidget(0, QFormLayout.LabelRole, self.localBranchLabel)

        self.localBranchEdit = QComboBox(PushDialog)
        self.localBranchEdit.setObjectName(u"localBranchEdit")
        sizePolicy = QSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.localBranchEdit.sizePolicy().hasHeightForWidth())
        self.localBranchEdit.setSizePolicy(sizePolicy)
        self.localBranchEdit.setInsertPolicy(QComboBox.NoInsert)

        self.formLayout.setWidget(0, QFormLayout.FieldRole, self.localBranchEdit)

        self.remoteBranchLabel = QLabel(PushDialog)
        self.remoteBranchLabel.setObjectName(u"remoteBranchLabel")

        self.formLayout.setWidget(1, QFormLayout.LabelRole, self.remoteBranchLabel)

        self.remoteBranchEdit = QComboBox(PushDialog)
        self.remoteBranchEdit.setObjectName(u"remoteBranchEdit")
        sizePolicy.setHeightForWidth(self.remoteBranchEdit.sizePolicy().hasHeightForWidth())
        self.remoteBranchEdit.setSizePolicy(sizePolicy)
        self.remoteBranchEdit.setInsertPolicy(QComboBox.NoInsert)
        self.remoteBranchEdit.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)

        self.formLayout.setWidget(1, QFormLayout.FieldRole, self.remoteBranchEdit)

        self.newRemoteBranchStackedWidget = QStackedWidget(PushDialog)
        self.newRemoteBranchStackedWidget.setObjectName(u"newRemoteBranchStackedWidget")
        self.newRemoteBranchPage0 = QWidget()
        self.newRemoteBranchPage0.setObjectName(u"newRemoteBranchPage0")
        self.horizontalLayout = QHBoxLayout(self.newRemoteBranchPage0)
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.horizontalLayout.setContentsMargins(0, 0, 0, 0)
        self.remoteNameLabel = QLabel(self.newRemoteBranchPage0)
        self.remoteNameLabel.setObjectName(u"remoteNameLabel")
        self.remoteNameLabel.setText(u"REMOTE/")

        self.horizontalLayout.addWidget(self.remoteNameLabel)

        self.newRemoteBranchNameEdit = QLineEdit(self.newRemoteBranchPage0)
        self.newRemoteBranchNameEdit.setObjectName(u"newRemoteBranchNameEdit")

        self.horizontalLayout.addWidget(self.newRemoteBranchNameEdit)

        self.newRemoteBranchStackedWidget.addWidget(self.newRemoteBranchPage0)
        self.newRemoteBranchPage1 = QWidget()
        self.newRemoteBranchPage1.setObjectName(u"newRemoteBranchPage1")
        self.verticalLayout_2 = QVBoxLayout(self.newRemoteBranchPage1)
        self.verticalLayout_2.setObjectName(u"verticalLayout_2")
        self.verticalLayout_2.setContentsMargins(0, 0, 0, 0)
        self.forcePushCheckBox = QCheckBox(self.newRemoteBranchPage1)
        self.forcePushCheckBox.setObjectName(u"forcePushCheckBox")

        self.verticalLayout_2.addWidget(self.forcePushCheckBox)

        self.newRemoteBranchStackedWidget.addWidget(self.newRemoteBranchPage1)

        self.formLayout.setWidget(2, QFormLayout.FieldRole, self.newRemoteBranchStackedWidget)

        self.trackCheckBox = QCheckBox(PushDialog)
        self.trackCheckBox.setObjectName(u"trackCheckBox")

        self.formLayout.setWidget(3, QFormLayout.FieldRole, self.trackCheckBox)

        self.trackingLabel = QLabel(PushDialog)
        self.trackingLabel.setObjectName(u"trackingLabel")
        sizePolicy1 = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.trackingLabel.sizePolicy().hasHeightForWidth())
        self.trackingLabel.setSizePolicy(sizePolicy1)
        self.trackingLabel.setText(u"<html><head/><body><p><span style=\" font-size:small;\">Extremely long local branch name will track an absurdly long remote branch name instead of another hilariously long remote branch name.</span></p></body></html>")
        self.trackingLabel.setTextFormat(Qt.RichText)
        self.trackingLabel.setAlignment(Qt.AlignLeading|Qt.AlignLeft|Qt.AlignTop)
        self.trackingLabel.setWordWrap(True)

        self.formLayout.setWidget(4, QFormLayout.FieldRole, self.trackingLabel)

        self.verticalSpacer = QSpacerItem(20, 8, QSizePolicy.Minimum, QSizePolicy.Preferred)

        self.formLayout.setItem(7, QFormLayout.LabelRole, self.verticalSpacer)

        self.groupBox = QGroupBox(PushDialog)
        self.groupBox.setObjectName(u"groupBox")
        sizePolicy2 = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(1)
        sizePolicy2.setHeightForWidth(self.groupBox.sizePolicy().hasHeightForWidth())
        self.groupBox.setSizePolicy(sizePolicy2)
        self.groupBox.setAlignment(Qt.AlignLeading|Qt.AlignLeft|Qt.AlignTop)
        self.verticalLayout = QVBoxLayout(self.groupBox)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.verticalLayout.setContentsMargins(0, 0, 0, 0)
        self.statusForm = StatusForm(self.groupBox)
        self.statusForm.setObjectName(u"statusForm")
        self.statusForm.setMinimumSize(QSize(0, 32))

        self.verticalLayout.addWidget(self.statusForm)


        self.formLayout.setWidget(8, QFormLayout.SpanningRole, self.groupBox)

        self.buttonBox = QDialogButtonBox(PushDialog)
        self.buttonBox.setObjectName(u"buttonBox")
        self.buttonBox.setOrientation(Qt.Horizontal)
        self.buttonBox.setStandardButtons(QDialogButtonBox.Cancel|QDialogButtonBox.Ok)

        self.formLayout.setWidget(18, QFormLayout.SpanningRole, self.buttonBox)

#if QT_CONFIG(shortcut)
        self.localBranchLabel.setBuddy(self.localBranchEdit)
        self.remoteBranchLabel.setBuddy(self.remoteBranchEdit)
#endif // QT_CONFIG(shortcut)
        QWidget.setTabOrder(self.localBranchEdit, self.remoteBranchEdit)
        QWidget.setTabOrder(self.remoteBranchEdit, self.forcePushCheckBox)
        QWidget.setTabOrder(self.forcePushCheckBox, self.newRemoteBranchNameEdit)
        QWidget.setTabOrder(self.newRemoteBranchNameEdit, self.trackCheckBox)

        self.retranslateUi(PushDialog)
        self.buttonBox.rejected.connect(PushDialog.reject)

        self.newRemoteBranchStackedWidget.setCurrentIndex(0)


        QMetaObject.connectSlotsByName(PushDialog)

    def retranslateUi(self, PushDialog):
        PushDialog.setWindowTitle(QCoreApplication.translate("PushDialog", u"Push branch", None))
        self.localBranchLabel.setText(QCoreApplication.translate("PushDialog", u"&Local branch", None))
        self.remoteBranchLabel.setText(QCoreApplication.translate("PushDialog", u"Push &to", None))
        self.newRemoteBranchNameEdit.setText("")
        self.newRemoteBranchNameEdit.setPlaceholderText(QCoreApplication.translate("PushDialog", u"Branch name on remote", None))
        self.forcePushCheckBox.setText(QCoreApplication.translate("PushDialog", u"&Force push", None))
        self.trackCheckBox.setText(QCoreApplication.translate("PushDialog", u"&Track this remote branch after pushing", None))
        self.groupBox.setTitle(QCoreApplication.translate("PushDialog", u"Status", None))
