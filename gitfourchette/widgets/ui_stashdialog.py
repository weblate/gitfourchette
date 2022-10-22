################################################################################
## Form generated from reading UI file 'stashdialog.ui'
##
## Created by: Qt User Interface Compiler version 5.15.6
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from gitfourchette.qt import *


class Ui_StashDialog(object):
    def setupUi(self, StashDialog):
        if not StashDialog.objectName():
            StashDialog.setObjectName(u"StashDialog")
        StashDialog.setWindowModality(Qt.NonModal)
        StashDialog.setEnabled(True)
        StashDialog.resize(543, 157)
        sizePolicy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(StashDialog.sizePolicy().hasHeightForWidth())
        StashDialog.setSizePolicy(sizePolicy)
        StashDialog.setSizeGripEnabled(False)
        StashDialog.setModal(True)
        self.formLayout = QFormLayout(StashDialog)
        self.formLayout.setObjectName(u"formLayout")
        self.formLayout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        self.messageLabel = QLabel(StashDialog)
        self.messageLabel.setObjectName(u"messageLabel")

        self.formLayout.setWidget(0, QFormLayout.LabelRole, self.messageLabel)

        self.messageEdit = QLineEdit(StashDialog)
        self.messageEdit.setObjectName(u"messageEdit")

        self.formLayout.setWidget(0, QFormLayout.FieldRole, self.messageEdit)

        self.optionsLabel = QLabel(StashDialog)
        self.optionsLabel.setObjectName(u"optionsLabel")

        self.formLayout.setWidget(1, QFormLayout.LabelRole, self.optionsLabel)

        self.keepIndexCheckBox = QCheckBox(StashDialog)
        self.keepIndexCheckBox.setObjectName(u"keepIndexCheckBox")

        self.formLayout.setWidget(1, QFormLayout.FieldRole, self.keepIndexCheckBox)

        self.includeUntrackedCheckBox = QCheckBox(StashDialog)
        self.includeUntrackedCheckBox.setObjectName(u"includeUntrackedCheckBox")

        self.formLayout.setWidget(2, QFormLayout.FieldRole, self.includeUntrackedCheckBox)

        self.includeIgnoredCheckBox = QCheckBox(StashDialog)
        self.includeIgnoredCheckBox.setObjectName(u"includeIgnoredCheckBox")

        self.formLayout.setWidget(3, QFormLayout.FieldRole, self.includeIgnoredCheckBox)

        self.buttonBox = QDialogButtonBox(StashDialog)
        self.buttonBox.setObjectName(u"buttonBox")
        self.buttonBox.setOrientation(Qt.Horizontal)
        self.buttonBox.setStandardButtons(QDialogButtonBox.Cancel|QDialogButtonBox.Ok)
        self.buttonBox.setCenterButtons(False)

        self.formLayout.setWidget(4, QFormLayout.FieldRole, self.buttonBox)

#if QT_CONFIG(shortcut)
        self.messageLabel.setBuddy(self.messageEdit)
#endif // QT_CONFIG(shortcut)

        self.retranslateUi(StashDialog)
        self.buttonBox.rejected.connect(StashDialog.reject)
        self.buttonBox.accepted.connect(StashDialog.accept)

        QMetaObject.connectSlotsByName(StashDialog)

    def retranslateUi(self, StashDialog):
        StashDialog.setWindowTitle(QCoreApplication.translate("StashDialog", u"New stash", None))
        self.messageLabel.setText(QCoreApplication.translate("StashDialog", u"&Description", None))
        self.optionsLabel.setText(QCoreApplication.translate("StashDialog", u"Options", None))
        self.keepIndexCheckBox.setText(QCoreApplication.translate("StashDialog", u"&Keep index", None))
        self.includeUntrackedCheckBox.setText(QCoreApplication.translate("StashDialog", u"Include &untracked", None))
        self.includeIgnoredCheckBox.setText(QCoreApplication.translate("StashDialog", u"Include &ignored", None))
