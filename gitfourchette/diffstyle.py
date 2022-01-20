from allqt import *
import colors
import settings


class DiffStyle:
    def __init__(self):
        self.monoFont = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        self.monoFont.setPointSize(9)
        if settings.prefs.diff_font:
            self.monoFont.fromString(settings.prefs.diff_font)
        self.monoFontMetrics = QFontMetricsF(self.monoFont)

        if settings.prefs.diff_colorblindFriendlyColors:
            self.minusColor = QColor(colors.orange)
            self.plusColor = QColor(colors.teal)
        else:
            self.minusColor = QColor(0xff5555)   # Lower-saturation alternative for e.g. foreground text: 0x993333
            self.plusColor = QColor(0x55ff55)   # Lower-saturation alternative for e.g. foreground text: 0x339933

        self.minusColor.setAlpha(0x58)
        self.plusColor.setAlpha(0x58)

        self.normalBF = QTextBlockFormat()
        self.normalCF = QTextCharFormat()
        self.normalCF.setFont(self.monoFont)

        self.plusBF = QTextBlockFormat()
        self.plusBF.setBackground(self.plusColor)
        self.plusCF = QTextCharFormat(self.normalCF)

        self.minusBF = QTextBlockFormat()
        self.minusBF.setBackground(self.minusColor)
        self.minusCF = QTextCharFormat(self.normalCF)

        self.arobaseFont = QFont()
        self.arobaseFont.setItalic(True)
        self.arobaseBF = QTextBlockFormat()
        self.arobaseCF = QTextCharFormat()
        self.arobaseCF.setFont(self.arobaseFont)
        self.arobaseCF.setForeground(QColor(0, 80, 240))

        self.warningFont1 = QFont()
        self.warningFont1.setBold(True)
        self.warningCF1 = QTextCharFormat()
        self.warningCF1.setForeground(QColor(200, 30, 0))
        self.warningCF1.setFont(self.warningFont1)
