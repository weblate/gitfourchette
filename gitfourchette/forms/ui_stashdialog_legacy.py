################################################################################
## Form generated from reading UI file 'stashdialog_legacy.ui'
##
## Created by: Qt User Interface Compiler version 6.4.2
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from gitfourchette.qt import *

class Ui_StashDialog_Legacy(object):
    def setupUi(self, StashDialog_Legacy):
        if not StashDialog_Legacy.objectName():
            StashDialog_Legacy.setObjectName(u"StashDialog_Legacy")
        StashDialog_Legacy.setWindowModality(Qt.NonModal)
        StashDialog_Legacy.setEnabled(True)
        StashDialog_Legacy.resize(543, 157)
        sizePolicy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(StashDialog_Legacy.sizePolicy().hasHeightForWidth())
        StashDialog_Legacy.setSizePolicy(sizePolicy)
        StashDialog_Legacy.setSizeGripEnabled(False)
        StashDialog_Legacy.setModal(True)
        self.formLayout = QFormLayout(StashDialog_Legacy)
        self.formLayout.setObjectName(u"formLayout")
        self.formLayout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        self.messageLabel = QLabel(StashDialog_Legacy)
        self.messageLabel.setObjectName(u"messageLabel")

        self.formLayout.setWidget(0, QFormLayout.LabelRole, self.messageLabel)

        self.messageEdit = QLineEdit(StashDialog_Legacy)
        self.messageEdit.setObjectName(u"messageEdit")

        self.formLayout.setWidget(0, QFormLayout.FieldRole, self.messageEdit)

        self.optionsLabel = QLabel(StashDialog_Legacy)
        self.optionsLabel.setObjectName(u"optionsLabel")

        self.formLayout.setWidget(1, QFormLayout.LabelRole, self.optionsLabel)

        self.keepIndexCheckBox = QCheckBox(StashDialog_Legacy)
        self.keepIndexCheckBox.setObjectName(u"keepIndexCheckBox")

        self.formLayout.setWidget(1, QFormLayout.FieldRole, self.keepIndexCheckBox)

        self.includeUntrackedCheckBox = QCheckBox(StashDialog_Legacy)
        self.includeUntrackedCheckBox.setObjectName(u"includeUntrackedCheckBox")
        self.includeUntrackedCheckBox.setChecked(True)

        self.formLayout.setWidget(2, QFormLayout.FieldRole, self.includeUntrackedCheckBox)

        self.includeIgnoredCheckBox = QCheckBox(StashDialog_Legacy)
        self.includeIgnoredCheckBox.setObjectName(u"includeIgnoredCheckBox")

        self.formLayout.setWidget(3, QFormLayout.FieldRole, self.includeIgnoredCheckBox)

        self.buttonBox = QDialogButtonBox(StashDialog_Legacy)
        self.buttonBox.setObjectName(u"buttonBox")
        self.buttonBox.setOrientation(Qt.Horizontal)
        self.buttonBox.setStandardButtons(QDialogButtonBox.Cancel|QDialogButtonBox.Ok)
        self.buttonBox.setCenterButtons(False)

        self.formLayout.setWidget(4, QFormLayout.FieldRole, self.buttonBox)

#if QT_CONFIG(shortcut)
        self.messageLabel.setBuddy(self.messageEdit)
#endif // QT_CONFIG(shortcut)

        self.retranslateUi(StashDialog_Legacy)
        self.buttonBox.rejected.connect(StashDialog_Legacy.reject)
        self.buttonBox.accepted.connect(StashDialog_Legacy.accept)

        QMetaObject.connectSlotsByName(StashDialog_Legacy)

    def retranslateUi(self, StashDialog_Legacy):
        StashDialog_Legacy.setWindowTitle(QCoreApplication.translate("StashDialog_Legacy", u"New stash", None))
        self.messageLabel.setText(QCoreApplication.translate("StashDialog_Legacy", u"&Description", None))
        self.messageEdit.setText("")
        self.messageEdit.setPlaceholderText(QCoreApplication.translate("StashDialog_Legacy", u"Optional stash message", None))
        self.optionsLabel.setText(QCoreApplication.translate("StashDialog_Legacy", u"Options", None))
#if QT_CONFIG(tooltip)
        self.keepIndexCheckBox.setToolTip(QCoreApplication.translate("StashDialog_Legacy", u"Tick this to leave all staged changes (already added to the index) intact in the working directory after stashing. They will be saved in the stash regardless.", None))
#endif // QT_CONFIG(tooltip)
        self.keepIndexCheckBox.setText(QCoreApplication.translate("StashDialog_Legacy", u"&Keep staged files in the working directory", None))
#if QT_CONFIG(tooltip)
        self.includeUntrackedCheckBox.setToolTip(QCoreApplication.translate("StashDialog_Legacy", u"All untracked files will also be stashed and then cleaned up from the working directory.", None))
#endif // QT_CONFIG(tooltip)
        self.includeUntrackedCheckBox.setText(QCoreApplication.translate("StashDialog_Legacy", u"Save &untracked files in the stash (new files that you haven\u2019t staged yet)", None))
#if QT_CONFIG(tooltip)
        self.includeIgnoredCheckBox.setToolTip(QCoreApplication.translate("StashDialog_Legacy", u"All ignored files will also be stashed and then cleaned up from the working directory.", None))
#endif // QT_CONFIG(tooltip)
        self.includeIgnoredCheckBox.setText(QCoreApplication.translate("StashDialog_Legacy", u"Save &ignored files in the stash", None))
