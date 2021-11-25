# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'commitdialog.ui'
##
## Created by: Qt User Interface Compiler version 5.15.2
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *


class Ui_CommitDialog(object):
    def setupUi(self, CommitDialog):
        if not CommitDialog.objectName():
            CommitDialog.setObjectName(u"CommitDialog")
        CommitDialog.resize(400, 200)
        CommitDialog.setModal(True)
        self.gridLayout = QGridLayout(CommitDialog)
        self.gridLayout.setObjectName(u"gridLayout")
        self.verticalLayout = QVBoxLayout()
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.summaryRowLayout = QHBoxLayout()
        self.summaryRowLayout.setObjectName(u"summaryRowLayout")
        self.summaryEditor = QLineEdit(CommitDialog)
        self.summaryEditor.setObjectName(u"summaryEditor")
        font = QFont()
        font.setPointSize(12)
        self.summaryEditor.setFont(font)

        self.summaryRowLayout.addWidget(self.summaryEditor)

        self.counterLabel = QLabel(CommitDialog)
        self.counterLabel.setObjectName(u"counterLabel")
        self.counterLabel.setEnabled(False)

        self.summaryRowLayout.addWidget(self.counterLabel)


        self.verticalLayout.addLayout(self.summaryRowLayout)

        self.descriptionEditor = QPlainTextEdit(CommitDialog)
        self.descriptionEditor.setObjectName(u"descriptionEditor")
        self.descriptionEditor.setTabChangesFocus(True)

        self.verticalLayout.addWidget(self.descriptionEditor)

        self.buttonBox = QDialogButtonBox(CommitDialog)
        self.buttonBox.setObjectName(u"buttonBox")
        self.buttonBox.setOrientation(Qt.Horizontal)
        self.buttonBox.setStandardButtons(QDialogButtonBox.Cancel|QDialogButtonBox.Ok)
        self.buttonBox.setCenterButtons(False)

        self.verticalLayout.addWidget(self.buttonBox)


        self.gridLayout.addLayout(self.verticalLayout, 0, 0, 1, 1)

        QWidget.setTabOrder(self.summaryEditor, self.descriptionEditor)

        self.retranslateUi(CommitDialog)
        self.buttonBox.accepted.connect(CommitDialog.accept)
        self.buttonBox.rejected.connect(CommitDialog.reject)

        QMetaObject.connectSlotsByName(CommitDialog)
    # setupUi

    def retranslateUi(self, CommitDialog):
        CommitDialog.setWindowTitle(QCoreApplication.translate("CommitDialog", u"Commit", None))
        self.summaryEditor.setPlaceholderText(QCoreApplication.translate("CommitDialog", u"Enter commit summary", None))
        self.counterLabel.setText(QCoreApplication.translate("CommitDialog", u"000", None))
        self.descriptionEditor.setPlaceholderText(QCoreApplication.translate("CommitDialog", u"Long-form description (optional)", None))
    # retranslateUi

