from PySide2.QtGui import *

import settings

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

warningFormat = QTextCharFormat()
warningFormat.setForeground(QColor(255, 0, 0))
warningFormat.setFont(settings.alternateFont)
