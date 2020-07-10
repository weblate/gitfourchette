from PySide2.QtGui import *

import settings
import colors

normalBF = QTextBlockFormat()
normalCF = QTextCharFormat()
normalCF.setFont(settings.monoFont)

plusBF = QTextBlockFormat()
plusCF = QTextCharFormat(normalCF)

minusBF = QTextBlockFormat()
minusCF = QTextCharFormat(normalCF)

if settings.prefs.diff_colorblindFriendlyColors:
    minusColor = QColor(colors.orange)
    plusColor  = QColor(colors.teal)
else:
    minusColor = QColor(0xff5555)   # Lower-saturation alternative for e.g. foreground text: 0x993333
    plusColor  = QColor(0x55ff55)   # Lower-saturation alternative for e.g. foreground text: 0x339933

minusColor.setAlpha(0x58)
plusColor.setAlpha(0x58)

plusBF.setBackground(plusColor)
minusBF.setBackground(minusColor)

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
