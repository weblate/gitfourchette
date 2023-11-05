################################################################################
## Form generated from reading UI file 'conflictview.ui'
##
## Created by: Qt User Interface Compiler version 6.6.0
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from gitfourchette.qt import *

class Ui_ConflictView(object):
    def setupUi(self, ConflictView):
        if not ConflictView.objectName():
            ConflictView.setObjectName(u"ConflictView")
        ConflictView.resize(555, 430)
        sizePolicy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.MinimumExpanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(ConflictView.sizePolicy().hasHeightForWidth())
        ConflictView.setSizePolicy(sizePolicy)
        self.verticalLayout = QVBoxLayout(ConflictView)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.titleLabel = QLabel(ConflictView)
        self.titleLabel.setObjectName(u"titleLabel")
        self.titleLabel.setAlignment(Qt.AlignCenter)
        self.titleLabel.setWordWrap(True)

        self.verticalLayout.addWidget(self.titleLabel)

        self.verticalSpacer_3 = QSpacerItem(20, 16, QSizePolicy.Minimum, QSizePolicy.Maximum)

        self.verticalLayout.addItem(self.verticalSpacer_3)

        self.subtitleLabel = QLabel(ConflictView)
        self.subtitleLabel.setObjectName(u"subtitleLabel")
        self.subtitleLabel.setText(u"blah blah blah blah blah blah blah blah blah blah blah blah blah blah blah blah blah blah blah blah blah blah blah blah blah blah blah blah blah blah blah blah blah blah blah blah blah blah blah ")
        self.subtitleLabel.setWordWrap(True)

        self.verticalLayout.addWidget(self.subtitleLabel)

        self.groupBox = QGroupBox(ConflictView)
        self.groupBox.setObjectName(u"groupBox")
        self.gridLayout_4 = QGridLayout(self.groupBox)
        self.gridLayout_4.setObjectName(u"gridLayout_4")
        self.radioTheirs = QRadioButton(self.groupBox)
        self.radioGroupBoth = QButtonGroup(ConflictView)
        self.radioGroupBoth.setObjectName(u"radioGroupBoth")
        self.radioGroupBoth.addButton(self.radioTheirs)
        self.radioTheirs.setObjectName(u"radioTheirs")

        self.gridLayout_4.addWidget(self.radioTheirs, 2, 0, 1, 1)

        self.radioDbuOurs = QRadioButton(self.groupBox)
        self.radioGroupDbu = QButtonGroup(ConflictView)
        self.radioGroupDbu.setObjectName(u"radioGroupDbu")
        self.radioGroupDbu.addButton(self.radioDbuOurs)
        self.radioDbuOurs.setObjectName(u"radioDbuOurs")

        self.gridLayout_4.addWidget(self.radioDbuOurs, 5, 0, 1, 1)

        self.radioTool = QRadioButton(self.groupBox)
        self.radioGroupBoth.addButton(self.radioTool)
        self.radioTool.setObjectName(u"radioTool")

        self.gridLayout_4.addWidget(self.radioTool, 3, 0, 1, 1)

        self.radioDbuTheirs = QRadioButton(self.groupBox)
        self.radioGroupDbu.addButton(self.radioDbuTheirs)
        self.radioDbuTheirs.setObjectName(u"radioDbuTheirs")

        self.gridLayout_4.addWidget(self.radioDbuTheirs, 4, 0, 1, 1)

        self.radioDbtOurs = QRadioButton(self.groupBox)
        self.radioGroupDbt = QButtonGroup(ConflictView)
        self.radioGroupDbt.setObjectName(u"radioGroupDbt")
        self.radioGroupDbt.addButton(self.radioDbtOurs)
        self.radioDbtOurs.setObjectName(u"radioDbtOurs")

        self.gridLayout_4.addWidget(self.radioDbtOurs, 6, 0, 1, 1)

        self.radioOurs = QRadioButton(self.groupBox)
        self.radioGroupBoth.addButton(self.radioOurs)
        self.radioOurs.setObjectName(u"radioOurs")

        self.gridLayout_4.addWidget(self.radioOurs, 0, 0, 1, 1)

        self.radioDbtTheirs = QRadioButton(self.groupBox)
        self.radioGroupDbt.addButton(self.radioDbtTheirs)
        self.radioDbtTheirs.setObjectName(u"radioDbtTheirs")

        self.gridLayout_4.addWidget(self.radioDbtTheirs, 7, 0, 1, 1)


        self.verticalLayout.addWidget(self.groupBox)

        self.confirmButton = QPushButton(ConflictView)
        self.confirmButton.setObjectName(u"confirmButton")
        self.confirmButton.setEnabled(False)

        self.verticalLayout.addWidget(self.confirmButton)

        self.explainer = QLabel(ConflictView)
        self.explainer.setObjectName(u"explainer")
        self.explainer.setAlignment(Qt.AlignLeading|Qt.AlignLeft|Qt.AlignTop)
        self.explainer.setWordWrap(True)

        self.verticalLayout.addWidget(self.explainer)

        self.verticalSpacer = QSpacerItem(20, 10, QSizePolicy.Minimum, QSizePolicy.Expanding)

        self.verticalLayout.addItem(self.verticalSpacer)


        self.retranslateUi(ConflictView)

        QMetaObject.connectSlotsByName(ConflictView)

    def retranslateUi(self, ConflictView):
        ConflictView.setWindowTitle(QCoreApplication.translate("ConflictView", u"Merge conflict", None))
        self.titleLabel.setText(QCoreApplication.translate("ConflictView", u"Merge conflict on \u201c{0}\u201d", None))
        self.groupBox.setTitle(QCoreApplication.translate("ConflictView", u"How do you want to solve this conflict?", None))
        self.radioTheirs.setText(QCoreApplication.translate("ConflictView", u"Use \u201ctheir\u201d version as is", None))
        self.radioDbuOurs.setText(QCoreApplication.translate("ConflictView", u"Don\u2019t add the file", None))
        self.radioTool.setText(QCoreApplication.translate("ConflictView", u"Merge in {tool}", None))
        self.radioDbuTheirs.setText(QCoreApplication.translate("ConflictView", u"Add \u201ctheir\u201d version back to our branch", None))
        self.radioDbtOurs.setText(QCoreApplication.translate("ConflictView", u"Keep \u201cour\u201d version intact", None))
        self.radioOurs.setText(QCoreApplication.translate("ConflictView", u"Keep \u201cour\u201d version intact", None))
        self.radioDbtTheirs.setText(QCoreApplication.translate("ConflictView", u"Delete the file", None))
        self.confirmButton.setText(QCoreApplication.translate("ConflictView", u"Select a resolution method", None))
        self.explainer.setText(QCoreApplication.translate("ConflictView", u"The conflict must be solved before you can commit the file.", None))
