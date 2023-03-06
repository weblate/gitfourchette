################################################################################
## Form generated from reading UI file 'searchwidget.ui'
##
## Created by: Qt User Interface Compiler version 6.4.2
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from gitfourchette.qt import *

class Ui_SearchWidget(object):
    def setupUi(self, SearchWidget):
        if not SearchWidget.objectName():
            SearchWidget.setObjectName(u"SearchWidget")
        SearchWidget.resize(329, 26)
        sizePolicy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(SearchWidget.sizePolicy().hasHeightForWidth())
        SearchWidget.setSizePolicy(sizePolicy)
        SearchWidget.setAutoFillBackground(True)
        self.horizontalLayout = QHBoxLayout(SearchWidget)
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.horizontalLayout.setContentsMargins(2, 2, 2, 2)
        self.lineEdit = QLineEdit(SearchWidget)
        self.lineEdit.setObjectName(u"lineEdit")

        self.horizontalLayout.addWidget(self.lineEdit)

        self.forwardButton = QToolButton(SearchWidget)
        self.forwardButton.setObjectName(u"forwardButton")
        self.forwardButton.setText(u"\u2193")

        self.horizontalLayout.addWidget(self.forwardButton)

        self.backwardButton = QToolButton(SearchWidget)
        self.backwardButton.setObjectName(u"backwardButton")
        self.backwardButton.setText(u"\u2191")

        self.horizontalLayout.addWidget(self.backwardButton)

        self.closeButton = QToolButton(SearchWidget)
        self.closeButton.setObjectName(u"closeButton")
        self.closeButton.setText(u"\u2573")

        self.horizontalLayout.addWidget(self.closeButton)


        self.retranslateUi(SearchWidget)

        QMetaObject.connectSlotsByName(SearchWidget)

    def retranslateUi(self, SearchWidget):
        SearchWidget.setWindowTitle(QCoreApplication.translate("SearchWidget", u"Form", None))
        self.lineEdit.setPlaceholderText(QCoreApplication.translate("SearchWidget", u"Find Commit", None))
#if QT_CONFIG(tooltip)
        self.forwardButton.setToolTip(QCoreApplication.translate("SearchWidget", u"Next Occurrence", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(tooltip)
        self.backwardButton.setToolTip(QCoreApplication.translate("SearchWidget", u"Previous Occurrence", None))
#endif // QT_CONFIG(tooltip)
#if QT_CONFIG(tooltip)
        self.closeButton.setToolTip(QCoreApplication.translate("SearchWidget", u"Close Search Bar", None))
#endif // QT_CONFIG(tooltip)
