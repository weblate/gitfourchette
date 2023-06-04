################################################################################
## Form generated from reading UI file 'conflictview.ui'
##
## Created by: Qt User Interface Compiler version 6.4.3
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

        self.reconcileStack = QStackedWidget(ConflictView)
        self.reconcileStack.setObjectName(u"reconcileStack")
        self.reconcile3Way = QWidget()
        self.reconcile3Way.setObjectName(u"reconcile3Way")
        self.horizontalLayout = QHBoxLayout(self.reconcile3Way)
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.groupBox = QGroupBox(self.reconcile3Way)
        self.groupBox.setObjectName(u"groupBox")
        self.verticalLayout = QVBoxLayout(self.groupBox)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.oursButton = QPushButton(self.groupBox)
        self.oursButton.setObjectName(u"oursButton")

        self.verticalLayout.addWidget(self.oursButton)

        self.theirsButton = QPushButton(self.groupBox)
        self.theirsButton.setObjectName(u"theirsButton")

        self.verticalLayout.addWidget(self.theirsButton)


        self.horizontalLayout.addWidget(self.groupBox)

        self.groupBox_2 = QGroupBox(self.reconcile3Way)
        self.groupBox_2.setObjectName(u"groupBox_2")
        self.verticalLayout_2 = QVBoxLayout(self.groupBox_2)
        self.verticalLayout_2.setObjectName(u"verticalLayout_2")
        self.mergeToolButton = QPushButton(self.groupBox_2)
        self.mergeToolButton.setObjectName(u"mergeToolButton")

        self.verticalLayout_2.addWidget(self.mergeToolButton)

        self.markSolvedButton = QPushButton(self.groupBox_2)
        self.markSolvedButton.setObjectName(u"markSolvedButton")
        self.markSolvedButton.setFlat(False)

        self.verticalLayout_2.addWidget(self.markSolvedButton)


        self.horizontalLayout.addWidget(self.groupBox_2)

        self.reconcileStack.addWidget(self.reconcile3Way)
        self.reconcileDeletedByUs = QWidget()
        self.reconcileDeletedByUs.setObjectName(u"reconcileDeletedByUs")
        self.gridLayout_2 = QGridLayout(self.reconcileDeletedByUs)
        self.gridLayout_2.setObjectName(u"gridLayout_2")
        self.deletedByUsDelete = QPushButton(self.reconcileDeletedByUs)
        self.deletedByUsDelete.setObjectName(u"deletedByUsDelete")

        self.gridLayout_2.addWidget(self.deletedByUsDelete, 4, 0, 1, 1)

        self.deletedByUsAdd = QPushButton(self.reconcileDeletedByUs)
        self.deletedByUsAdd.setObjectName(u"deletedByUsAdd")

        self.gridLayout_2.addWidget(self.deletedByUsAdd, 2, 0, 1, 1)

        self.deletedByUsText = QLabel(self.reconcileDeletedByUs)
        self.deletedByUsText.setObjectName(u"deletedByUsText")
        self.deletedByUsText.setWordWrap(True)

        self.gridLayout_2.addWidget(self.deletedByUsText, 0, 0, 1, 1)

        self.reconcileStack.addWidget(self.reconcileDeletedByUs)

        self.gridLayout.addWidget(self.reconcileStack, 5, 0, 1, 1)

        self.verticalSpacer_2 = QSpacerItem(20, 30, QSizePolicy.Minimum, QSizePolicy.Expanding)

        self.gridLayout.addItem(self.verticalSpacer_2, 4, 0, 1, 1)

        self.titleLabel = QLabel(ConflictView)
        self.titleLabel.setObjectName(u"titleLabel")
        self.titleLabel.setAlignment(Qt.AlignCenter)

        self.gridLayout.addWidget(self.titleLabel, 2, 0, 1, 2)

        self.verticalSpacer = QSpacerItem(20, 100, QSizePolicy.Minimum, QSizePolicy.Expanding)

        self.gridLayout.addItem(self.verticalSpacer, 7, 0, 1, 1)


        self.retranslateUi(ConflictView)

        self.reconcileStack.setCurrentIndex(0)


        QMetaObject.connectSlotsByName(ConflictView)

    def retranslateUi(self, ConflictView):
        ConflictView.setWindowTitle(QCoreApplication.translate("ConflictView", u"Merge conflict", None))
        self.label_2.setText(QCoreApplication.translate("ConflictView", u"You must solve the conflict before you can commit the file.", None))
        self.groupBox.setTitle(QCoreApplication.translate("ConflictView", u"One-click reconcile", None))
        self.oursButton.setText(QCoreApplication.translate("ConflictView", u"Use ours", None))
        self.theirsButton.setText(QCoreApplication.translate("ConflictView", u"Use theirs", None))
        self.groupBox_2.setTitle(QCoreApplication.translate("ConflictView", u"Reconcile manually", None))
        self.mergeToolButton.setText(QCoreApplication.translate("ConflictView", u"Merge in {0}", None))
        self.markSolvedButton.setText(QCoreApplication.translate("ConflictView", u"Mark as resolved", None))
        self.deletedByUsDelete.setText(QCoreApplication.translate("ConflictView", u"Don\u2019t add", None))
        self.deletedByUsAdd.setText(QCoreApplication.translate("ConflictView", u"Add \u201c{0}\u201d to our branch", None))
        self.deletedByUsText.setText(QCoreApplication.translate("ConflictView", u"<b>Deleted by us:</b> \u201c{0}\u201d has been deleted from our branch, but it still exists in the branch that we\u2019re merging. While the file was gone from our side, the other branch has modified it.", None))
        self.titleLabel.setText(QCoreApplication.translate("ConflictView", u"Merge conflict", None))
