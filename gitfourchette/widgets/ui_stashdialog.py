################################################################################
## Form generated from reading UI file 'stashdialog.ui'
##
## Created by: Qt User Interface Compiler version 6.4.2
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
        StashDialog.resize(461, 432)
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

        self.cleanupCheckBox = QCheckBox(StashDialog)
        self.cleanupCheckBox.setObjectName(u"cleanupCheckBox")
        self.cleanupCheckBox.setChecked(True)

        self.formLayout.setWidget(1, QFormLayout.FieldRole, self.cleanupCheckBox)

        self.line = QFrame(StashDialog)
        self.line.setObjectName(u"line")
        self.line.setFrameShape(QFrame.HLine)
        self.line.setFrameShadow(QFrame.Sunken)

        self.formLayout.setWidget(3, QFormLayout.SpanningRole, self.line)

        self.willBackUpChangesLabel = QLabel(StashDialog)
        self.willBackUpChangesLabel.setObjectName(u"willBackUpChangesLabel")

        self.formLayout.setWidget(4, QFormLayout.SpanningRole, self.willBackUpChangesLabel)

        self.willRemoveChangesLabel = QLabel(StashDialog)
        self.willRemoveChangesLabel.setObjectName(u"willRemoveChangesLabel")

        self.formLayout.setWidget(5, QFormLayout.SpanningRole, self.willRemoveChangesLabel)

        self.willKeepChangesLabel = QLabel(StashDialog)
        self.willKeepChangesLabel.setObjectName(u"willKeepChangesLabel")

        self.formLayout.setWidget(6, QFormLayout.SpanningRole, self.willKeepChangesLabel)

        self.fileList = QListWidget(StashDialog)
        self.fileList.setObjectName(u"fileList")
        self.fileList.setSelectionMode(QAbstractItemView.ExtendedSelection)

        self.formLayout.setWidget(7, QFormLayout.FieldRole, self.fileList)

        self.buttonBox = QDialogButtonBox(StashDialog)
        self.buttonBox.setObjectName(u"buttonBox")
        self.buttonBox.setOrientation(Qt.Horizontal)
        self.buttonBox.setStandardButtons(QDialogButtonBox.Cancel|QDialogButtonBox.Ok)
        self.buttonBox.setCenterButtons(False)

        self.formLayout.setWidget(17, QFormLayout.FieldRole, self.buttonBox)

        self.indexAndWtWarning = QLabel(StashDialog)
        self.indexAndWtWarning.setObjectName(u"indexAndWtWarning")
        self.indexAndWtWarning.setWordWrap(True)

        self.formLayout.setWidget(8, QFormLayout.SpanningRole, self.indexAndWtWarning)

#if QT_CONFIG(shortcut)
        self.messageLabel.setBuddy(self.messageEdit)
#endif // QT_CONFIG(shortcut)

        self.retranslateUi(StashDialog)
        self.buttonBox.rejected.connect(StashDialog.reject)
        self.buttonBox.accepted.connect(StashDialog.accept)
        self.cleanupCheckBox.clicked["bool"].connect(self.willRemoveChangesLabel.setVisible)
        self.cleanupCheckBox.clicked["bool"].connect(self.willKeepChangesLabel.setHidden)

        QMetaObject.connectSlotsByName(StashDialog)

    def retranslateUi(self, StashDialog):
        StashDialog.setWindowTitle(QCoreApplication.translate("StashDialog", u"New stash", None))
        self.messageLabel.setText(QCoreApplication.translate("StashDialog", u"&Description", None))
        self.messageEdit.setPlaceholderText(QCoreApplication.translate("StashDialog", u"Optional stash message", None))
        self.optionsLabel.setText(QCoreApplication.translate("StashDialog", u"Options", None))
#if QT_CONFIG(tooltip)
        self.cleanupCheckBox.setToolTip(QCoreApplication.translate("StashDialog", u"Normally, stashed changes are removed from the working directory.\n"
"Untick this to leave the stashed changes intact instead.", None))
#endif // QT_CONFIG(tooltip)
        self.cleanupCheckBox.setText(QCoreApplication.translate("StashDialog", u"&Remove stashed changes after stashing", None))
        self.willBackUpChangesLabel.setText(QCoreApplication.translate("StashDialog", u"The stash will back up all changes to the files ticked below.", None))
        self.willRemoveChangesLabel.setText(QCoreApplication.translate("StashDialog", u"These changes will then be removed from the working directory.", None))
        self.willKeepChangesLabel.setText(QCoreApplication.translate("StashDialog", u"These changes will remain in the working directory.", None))
        self.indexAndWtWarning.setText(QCoreApplication.translate("StashDialog", u"Warning: Some of the files have both staged and unstaged changes. Those changes will be combined in the stash.", None))
