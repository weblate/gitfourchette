################################################################################
## Form generated from reading UI file 'commitdialog.ui'
##
## Created by: Qt User Interface Compiler version 6.4.3
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from gitfourchette.qt import *

from gitfourchette.forms.signatureform import SignatureForm

class Ui_CommitDialog(object):
    def setupUi(self, CommitDialog):
        if not CommitDialog.objectName():
            CommitDialog.setObjectName(u"CommitDialog")
        CommitDialog.resize(512, 208)
        CommitDialog.setModal(True)
        self.verticalLayout = QVBoxLayout(CommitDialog)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.summaryRowLayout = QHBoxLayout()
        self.summaryRowLayout.setObjectName(u"summaryRowLayout")
        self.summaryEditor = QLineEdit(CommitDialog)
        self.summaryEditor.setObjectName(u"summaryEditor")

        self.summaryRowLayout.addWidget(self.summaryEditor)

        self.counterLabel = QLabel(CommitDialog)
        self.counterLabel.setObjectName(u"counterLabel")
        self.counterLabel.setEnabled(False)
        self.counterLabel.setText(u"000")

        self.summaryRowLayout.addWidget(self.counterLabel)


        self.verticalLayout.addLayout(self.summaryRowLayout)

        self.descriptionEditor = QPlainTextEdit(CommitDialog)
        self.descriptionEditor.setObjectName(u"descriptionEditor")
        self.descriptionEditor.setTabChangesFocus(True)

        self.verticalLayout.addWidget(self.descriptionEditor)

        self.revealAuthor = QCheckBox(CommitDialog)
        self.revealAuthor.setObjectName(u"revealAuthor")
        self.revealAuthor.setChecked(False)

        self.verticalLayout.addWidget(self.revealAuthor)

        self.authorGroupBox = QGroupBox(CommitDialog)
        self.authorGroupBox.setObjectName(u"authorGroupBox")
        self.authorGroupBox.setEnabled(True)
        self.authorGroupBox.setFlat(False)
        self.authorGroupBox.setCheckable(False)
        self.verticalLayout_2 = QVBoxLayout(self.authorGroupBox)
        self.verticalLayout_2.setObjectName(u"verticalLayout_2")
        self.authorSignature = SignatureForm(self.authorGroupBox)
        self.authorSignature.setObjectName(u"authorSignature")

        self.verticalLayout_2.addWidget(self.authorSignature)

        self.overrideCommitterSignature = QCheckBox(self.authorGroupBox)
        self.overrideCommitterSignature.setObjectName(u"overrideCommitterSignature")
        self.overrideCommitterSignature.setChecked(False)

        self.verticalLayout_2.addWidget(self.overrideCommitterSignature)


        self.verticalLayout.addWidget(self.authorGroupBox)

        self.detachedHeadWarning = QLabel(CommitDialog)
        self.detachedHeadWarning.setObjectName(u"detachedHeadWarning")
        font = QFont()
        font.setBold(True)
        self.detachedHeadWarning.setFont(font)
        self.detachedHeadWarning.setWordWrap(True)

        self.verticalLayout.addWidget(self.detachedHeadWarning)

        self.buttonBox = QDialogButtonBox(CommitDialog)
        self.buttonBox.setObjectName(u"buttonBox")
        self.buttonBox.setOrientation(Qt.Horizontal)
        self.buttonBox.setStandardButtons(QDialogButtonBox.Cancel|QDialogButtonBox.Ok)
        self.buttonBox.setCenterButtons(False)

        self.verticalLayout.addWidget(self.buttonBox)

        QWidget.setTabOrder(self.summaryEditor, self.descriptionEditor)

        self.retranslateUi(CommitDialog)
        self.buttonBox.accepted.connect(CommitDialog.accept)
        self.buttonBox.rejected.connect(CommitDialog.reject)
        self.revealAuthor.toggled.connect(self.authorGroupBox.setVisible)
        self.revealAuthor.toggled.connect(self.authorGroupBox.setEnabled)

        QMetaObject.connectSlotsByName(CommitDialog)

    def retranslateUi(self, CommitDialog):
        CommitDialog.setWindowTitle(QCoreApplication.translate("CommitDialog", u"Commit", None))
        self.summaryEditor.setPlaceholderText(QCoreApplication.translate("CommitDialog", u"Enter commit summary", None))
        self.descriptionEditor.setPlaceholderText(QCoreApplication.translate("CommitDialog", u"Long-form description (optional)", None))
        self.revealAuthor.setText(QCoreApplication.translate("CommitDialog", u"&Edit author", None))
        self.authorGroupBox.setTitle("")
#if QT_CONFIG(tooltip)
        self.overrideCommitterSignature.setToolTip(QCoreApplication.translate("CommitDialog", u"<p>Check this to use the same custom signature for the author and committer.</p>\n"
"<p>If you uncheck this, only the author will be overridden, and the committer will be set to: {0}.</p>", None))
#endif // QT_CONFIG(tooltip)
        self.overrideCommitterSignature.setText(QCoreApplication.translate("CommitDialog", u"Also override committer signature", None))
        self.detachedHeadWarning.setText(QCoreApplication.translate("CommitDialog", u"Warning: You are not in any branch (detached HEAD). You should create a branch to ensure your commit won\u2019t be lost inadvertently.", None))
