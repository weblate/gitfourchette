################################################################################
## Form generated from reading UI file 'searchbar.ui'
##
## Created by: Qt User Interface Compiler version 6.4.3
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from gitfourchette.qt import *

class Ui_SearchBar(object):
    def setupUi(self, SearchBar):
        if not SearchBar.objectName():
            SearchBar.setObjectName(u"SearchBar")
        SearchBar.resize(329, 26)
        sizePolicy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(SearchBar.sizePolicy().hasHeightForWidth())
        SearchBar.setSizePolicy(sizePolicy)
        SearchBar.setAutoFillBackground(True)
        self.horizontalLayout = QHBoxLayout(SearchBar)
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.horizontalLayout.setContentsMargins(2, 2, 2, 2)
        self.lineEdit = QLineEdit(SearchBar)
        self.lineEdit.setObjectName(u"lineEdit")
        self.lineEdit.setClearButtonEnabled(True)

        self.horizontalLayout.addWidget(self.lineEdit)

        self.forwardButton = QToolButton(SearchBar)
        self.forwardButton.setObjectName(u"forwardButton")
        self.forwardButton.setText(u"\u2193")

        self.horizontalLayout.addWidget(self.forwardButton)

        self.backwardButton = QToolButton(SearchBar)
        self.backwardButton.setObjectName(u"backwardButton")
        self.backwardButton.setText(u"\u2191")

        self.horizontalLayout.addWidget(self.backwardButton)

        self.closeButton = QToolButton(SearchBar)
        self.closeButton.setObjectName(u"closeButton")
        self.closeButton.setText(u"\u2573")

        self.horizontalLayout.addWidget(self.closeButton)


        self.retranslateUi(SearchBar)

        QMetaObject.connectSlotsByName(SearchBar)

    def retranslateUi(self, SearchBar):
        SearchBar.setWindowTitle(QCoreApplication.translate("SearchBar", u"Search", None))
        self.lineEdit.setPlaceholderText(QCoreApplication.translate("SearchBar", u"Search...", None))
#if QT_CONFIG(tooltip)
        self.forwardButton.setToolTip(QCoreApplication.translate("SearchBar", u"Next Occurrence", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(tooltip)
        self.backwardButton.setToolTip(QCoreApplication.translate("SearchBar", u"Previous Occurrence", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(tooltip)
        self.closeButton.setToolTip(QCoreApplication.translate("SearchBar", u"Close Search Bar", None))
#endif // QT_CONFIG(tooltip)
