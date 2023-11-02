################################################################################
## Form generated from reading UI file 'absorbsubmodule.ui'
##
## Created by: Qt User Interface Compiler version 6.6.0
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from gitfourchette.qt import *

class Ui_AbsorbSubmodule(object):
    def setupUi(self, AbsorbSubmodule):
        if not AbsorbSubmodule.objectName():
            AbsorbSubmodule.setObjectName(u"AbsorbSubmodule")
        AbsorbSubmodule.resize(321, 204)
        sizePolicy = QSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.MinimumExpanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(AbsorbSubmodule.sizePolicy().hasHeightForWidth())
        AbsorbSubmodule.setSizePolicy(sizePolicy)
        self.verticalLayout = QVBoxLayout(AbsorbSubmodule)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.label1 = QLabel(AbsorbSubmodule)
        self.label1.setObjectName(u"label1")
        sizePolicy1 = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.label1.sizePolicy().hasHeightForWidth())
        self.label1.setSizePolicy(sizePolicy1)
        self.label1.setWordWrap(True)

        self.verticalLayout.addWidget(self.label1)

        self.widget = QWidget(AbsorbSubmodule)
        self.widget.setObjectName(u"widget")
        self.horizontalLayout = QHBoxLayout(self.widget)
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.label = QLabel(self.widget)
        self.label.setObjectName(u"label")
        sizePolicy2 = QSizePolicy(QSizePolicy.Minimum, QSizePolicy.Preferred)
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.label.sizePolicy().hasHeightForWidth())
        self.label.setSizePolicy(sizePolicy2)

        self.horizontalLayout.addWidget(self.label)

        self.comboBox = QComboBox(self.widget)
        self.comboBox.addItem("")
        self.comboBox.setObjectName(u"comboBox")
        sizePolicy3 = QSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)
        sizePolicy3.setHorizontalStretch(0)
        sizePolicy3.setVerticalStretch(0)
        sizePolicy3.setHeightForWidth(self.comboBox.sizePolicy().hasHeightForWidth())
        self.comboBox.setSizePolicy(sizePolicy3)

        self.horizontalLayout.addWidget(self.comboBox)


        self.verticalLayout.addWidget(self.widget)

        self.label2 = QLabel(AbsorbSubmodule)
        self.label2.setObjectName(u"label2")
        sizePolicy1.setHeightForWidth(self.label2.sizePolicy().hasHeightForWidth())
        self.label2.setSizePolicy(sizePolicy1)
        self.label2.setWordWrap(True)

        self.verticalLayout.addWidget(self.label2)

        self.buttonBox = QDialogButtonBox(AbsorbSubmodule)
        self.buttonBox.setObjectName(u"buttonBox")
        self.buttonBox.setOrientation(Qt.Horizontal)
        self.buttonBox.setStandardButtons(QDialogButtonBox.Cancel|QDialogButtonBox.Ok)

        self.verticalLayout.addWidget(self.buttonBox)


        self.retranslateUi(AbsorbSubmodule)
        self.buttonBox.accepted.connect(AbsorbSubmodule.accept)
        self.buttonBox.rejected.connect(AbsorbSubmodule.reject)

        QMetaObject.connectSlotsByName(AbsorbSubmodule)

    def retranslateUi(self, AbsorbSubmodule):
        AbsorbSubmodule.setWindowTitle(QCoreApplication.translate("AbsorbSubmodule", u"Absorb submodule", None))
        self.label1.setText(QCoreApplication.translate("AbsorbSubmodule", u"Do you want the Git repository \u201c{sub}\u201d to be absorbed as a submodule of \u201c{super}\u201d?", None))
        self.label.setText(QCoreApplication.translate("AbsorbSubmodule", u"Submodule remote:", None))
        self.comboBox.setItemText(0, QCoreApplication.translate("AbsorbSubmodule", u"origin", None))

        self.label2.setText(QCoreApplication.translate("AbsorbSubmodule", u"If you choose to proceed, \u201c{super}\u201d will assume control of the \u201c.git\u201d directory in \u201c{sub}\u201d. You will not be able to use \u201c{sub}\u201d as an independent repository. This cannot be undone!", None))
