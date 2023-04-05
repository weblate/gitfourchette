################################################################################
## Form generated from reading UI file 'conflictview.ui'
##
## Created by: Qt User Interface Compiler version 6.4.2
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from gitfourchette.qt import *

class Ui_ConflictView(object):
    def setupUi(self, ConflictView):
        if not ConflictView.objectName():
            ConflictView.setObjectName(u"ConflictView")
        ConflictView.resize(555, 333)
        self.gridLayout = QGridLayout(ConflictView)
        self.gridLayout.setObjectName(u"gridLayout")
        self.label_2 = QLabel(ConflictView)
        self.label_2.setObjectName(u"label_2")
        self.label_2.setAlignment(Qt.AlignCenter)
        self.label_2.setWordWrap(True)

        self.gridLayout.addWidget(self.label_2, 3, 0, 1, 2)

        self.verticalSpacer = QSpacerItem(20, 100, QSizePolicy.Minimum, QSizePolicy.Expanding)

        self.gridLayout.addItem(self.verticalSpacer, 6, 0, 1, 1)

        self.groupBox = QGroupBox(ConflictView)
        self.groupBox.setObjectName(u"groupBox")
        self.verticalLayout = QVBoxLayout(self.groupBox)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.oursButton = QPushButton(self.groupBox)
        self.oursButton.setObjectName(u"oursButton")

        self.verticalLayout.addWidget(self.oursButton)

        self.theirsButton = QPushButton(self.groupBox)
        self.theirsButton.setObjectName(u"theirsButton")

        self.verticalLayout.addWidget(self.theirsButton)


        self.gridLayout.addWidget(self.groupBox, 5, 0, 1, 1)

        self.titleLabel = QLabel(ConflictView)
        self.titleLabel.setObjectName(u"titleLabel")
        self.titleLabel.setAlignment(Qt.AlignCenter)

        self.gridLayout.addWidget(self.titleLabel, 2, 0, 1, 2)

        self.verticalSpacer_2 = QSpacerItem(20, 30, QSizePolicy.Minimum, QSizePolicy.Expanding)

        self.gridLayout.addItem(self.verticalSpacer_2, 4, 0, 1, 1)

        self.groupBox_2 = QGroupBox(ConflictView)
        self.groupBox_2.setObjectName(u"groupBox_2")
        self.verticalLayout_2 = QVBoxLayout(self.groupBox_2)
        self.verticalLayout_2.setObjectName(u"verticalLayout_2")
        self.mergeToolButton = QPushButton(self.groupBox_2)
        self.mergeToolButton.setObjectName(u"mergeToolButton")

        self.verticalLayout_2.addWidget(self.mergeToolButton)

        self.editFileButton = QPushButton(self.groupBox_2)
        self.editFileButton.setObjectName(u"editFileButton")

        self.verticalLayout_2.addWidget(self.editFileButton)

        self.markSolvedButton = QPushButton(self.groupBox_2)
        self.markSolvedButton.setObjectName(u"markSolvedButton")
        self.markSolvedButton.setFlat(False)

        self.verticalLayout_2.addWidget(self.markSolvedButton)


        self.gridLayout.addWidget(self.groupBox_2, 5, 1, 1, 1)


        self.retranslateUi(ConflictView)

        QMetaObject.connectSlotsByName(ConflictView)

    def retranslateUi(self, ConflictView):
        ConflictView.setWindowTitle(QCoreApplication.translate("ConflictView", u"Merge conflict", None))
        self.label_2.setText(QCoreApplication.translate("ConflictView", u"You must solve the conflict before you can commit the file.", None))
        self.groupBox.setTitle(QCoreApplication.translate("ConflictView", u"One-click reconcile", None))
        self.oursButton.setText(QCoreApplication.translate("ConflictView", u"Use ours", None))
        self.theirsButton.setText(QCoreApplication.translate("ConflictView", u"Use theirs", None))
        self.titleLabel.setText(QCoreApplication.translate("ConflictView", u"Merge conflict", None))
        self.groupBox_2.setTitle(QCoreApplication.translate("ConflictView", u"Reconcile manually", None))
        self.mergeToolButton.setText(QCoreApplication.translate("ConflictView", u"Merge in {0}", None))
        self.editFileButton.setText(QCoreApplication.translate("ConflictView", u"Edit file", None))
        self.markSolvedButton.setText(QCoreApplication.translate("ConflictView", u"Mark as resolved", None))
