from PySide2.QtGui import *

import settings
import colors

normalBF = QTextBlockFormat()
normalCF = QTextCharFormat()
normalCF.setFont(settings.monoFont)

plusBF = QTextBlockFormat()
plusBF.setBackground(QColor(220, 254, 225))
plusCF = normalCF

minusBF = QTextBlockFormat()
minusBF.setBackground(QColor(255, 227, 228))
minusCF = normalCF

arobaseBF = QTextBlockFormat()
arobaseCF = QTextCharFormat()
arobaseCF.setFont(settings.alternateFont)
arobaseCF.setForeground(QColor(0, 80, 240))

warningFormat1 = QTextCharFormat()
warningFormat1.setForeground(QColor(200, 30, 0))
warningFormat1.setFont(settings.boldFont)

warningFormat2 = QTextCharFormat()
warningFormat2.setForeground(QColor(200, 30, 0))
#warningFormat2.setFont(settings.alternateFont)
