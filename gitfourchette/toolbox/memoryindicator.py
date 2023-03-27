from gitfourchette.qt import *
import gc
import os
import time

try:
    import psutil
except ImportError:
    print("psutil isn't available. The memory indicator will not work.")
    psutil = None


class MemoryIndicator(QPushButton):
    def __init__(self, parent):
        super().__init__(parent)
        self.setText("Memory")

        # No border: don't let it thicken the status bar
        self.setStyleSheet("border: none; text-align: right; padding-right: 8px;")

        font: QFont = self.font()
        font.setPointSize(font.pointSize() * 85 // 100)
        if MACOS:
            font.setFamily("Helvetica Neue")  # fixed-width numbers
        self.setFont(font)

        width = self.fontMetrics().horizontalAdvance("9,999m  9,999k  9,999q")

        self.setMinimumWidth(width)
        self.setMaximumWidth(width)
        self.clicked.connect(self.onMemoryIndicatorClicked)
        self.setToolTip("Force GC")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.lastUpdate = 0

    def onMemoryIndicatorClicked(self):
        gc.collect()

        print("Top-Level Windows:")
        for tlw in QApplication.topLevelWindows():
            print("*", tlw)
        print("Top-Level Widgets:")
        for tlw in QApplication.topLevelWidgets():
            print("*", tlw, tlw.objectName())
        print()

        self.updateMemoryIndicator()

    def paintEvent(self, e):
        self.updateMemoryIndicator()
        super().paintEvent(e)

    def updateMemoryIndicator(self):
        now = time.time()
        if now - self.lastUpdate < 0.03:
            return
        self.lastUpdate = time.time()

        numQObjects = sum(1 + len(tlw.findChildren(QObject))  # "+1" to account for tlw itself
                          for tlw in QApplication.topLevelWidgets())

        rssStr = ""
        if psutil:
            rss = psutil.Process(os.getpid()).memory_info().rss
            rssStr = F"{rss>>20:,}m"
        self.setText(F"{rssStr} {len(gc.get_objects())//1000:,}k {numQObjects:,}q")
