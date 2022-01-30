from allqt import *


################################################################################
## Form generated from reading UI file 'clonedialog.ui'
##
## Created by: Qt User Interface Compiler version 5.15.2
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################


from widgets.statusform import StatusForm


class Ui_CloneDialog(object):
    def setupUi(self, CloneDialog):
        if not CloneDialog.objectName():
            CloneDialog.setObjectName(u"CloneDialog")
        CloneDialog.setWindowModality(Qt.NonModal)
        CloneDialog.setEnabled(True)
        CloneDialog.resize(505, 227)
        sizePolicy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(CloneDialog.sizePolicy().hasHeightForWidth())
        CloneDialog.setSizePolicy(sizePolicy)
        CloneDialog.setSizeGripEnabled(False)
        CloneDialog.setModal(True)
        self.formLayout = QFormLayout(CloneDialog)
        self.formLayout.setObjectName(u"formLayout")
        self.urlLabel = QLabel(CloneDialog)
        self.urlLabel.setObjectName(u"urlLabel")

        self.formLayout.setWidget(1, QFormLayout.LabelRole, self.urlLabel)

        self.pathLabel = QLabel(CloneDialog)
        self.pathLabel.setObjectName(u"pathLabel")

        self.formLayout.setWidget(2, QFormLayout.LabelRole, self.pathLabel)

        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.pathEdit = QLineEdit(CloneDialog)
        self.pathEdit.setObjectName(u"pathEdit")

        self.horizontalLayout.addWidget(self.pathEdit)

        self.browseButton = QPushButton(CloneDialog)
        self.browseButton.setObjectName(u"browseButton")

        self.horizontalLayout.addWidget(self.browseButton)


        self.formLayout.setLayout(2, QFormLayout.FieldRole, self.horizontalLayout)

        self.label = QLabel(CloneDialog)
        self.label.setObjectName(u"label")

        self.formLayout.setWidget(3, QFormLayout.LabelRole, self.label)

        self.buttonBox = QDialogButtonBox(CloneDialog)
        self.buttonBox.setObjectName(u"buttonBox")
        self.buttonBox.setOrientation(Qt.Horizontal)
        self.buttonBox.setStandardButtons(QDialogButtonBox.Cancel|QDialogButtonBox.Ok)
        self.buttonBox.setCenterButtons(False)

        self.formLayout.setWidget(5, QFormLayout.FieldRole, self.buttonBox)

        self.groupBox = QGroupBox(CloneDialog)
        self.groupBox.setObjectName(u"groupBox")
        sizePolicy1 = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.groupBox.sizePolicy().hasHeightForWidth())
        self.groupBox.setSizePolicy(sizePolicy1)
        self.verticalLayout = QVBoxLayout(self.groupBox)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.statusForm = StatusForm(self.groupBox)
        self.statusForm.setObjectName(u"statusForm")

        self.verticalLayout.addWidget(self.statusForm)


        self.formLayout.setWidget(3, QFormLayout.FieldRole, self.groupBox)

        self.urlEdit = QComboBox(CloneDialog)
        self.urlEdit.setObjectName(u"urlEdit")
        sizePolicy2 = QSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.urlEdit.sizePolicy().hasHeightForWidth())
        self.urlEdit.setSizePolicy(sizePolicy2)
        self.urlEdit.setEditable(True)
        self.urlEdit.setInsertPolicy(QComboBox.NoInsert)

        self.formLayout.setWidget(1, QFormLayout.FieldRole, self.urlEdit)

        QWidget.setTabOrder(self.urlEdit, self.pathEdit)
        QWidget.setTabOrder(self.pathEdit, self.browseButton)

        self.retranslateUi(CloneDialog)
        self.buttonBox.rejected.connect(CloneDialog.reject)

        QMetaObject.connectSlotsByName(CloneDialog)
    # setupUi

    def retranslateUi(self, CloneDialog):
        CloneDialog.setWindowTitle(QCoreApplication.translate("CloneDialog", u"Clone repository", None))
        self.urlLabel.setText(QCoreApplication.translate("CloneDialog", u"Remote URL", None))
        self.pathLabel.setText(QCoreApplication.translate("CloneDialog", u"Clone into", None))
        self.browseButton.setText(QCoreApplication.translate("CloneDialog", u"&Browse...", None))
        self.label.setText(QCoreApplication.translate("CloneDialog", u"Status", None))
        self.groupBox.setTitle("")
    # retranslateUi
