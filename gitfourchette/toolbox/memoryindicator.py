import gc
import logging
import os
import textwrap
import time

from gitfourchette.qt import *

try:
    import psutil
except ImportError:
    psutil = None

logger = logging.getLogger(__name__)


class MemoryIndicator(QPushButton):
    def __init__(self, parent):
        super().__init__(parent)

        self.setObjectName("MemoryIndicator")
        self.setText("Memory")

        if not psutil:
            logger.info("psutil isn't available. Some information will be missing from the memory indicator.")

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

        windows = '\n'.join(f'\t* {w.__class__.__name__} {w.objectName()}' for w in QApplication.topLevelWindows())
        widgets = '\n'.join(f'\t* {w.__class__.__name__} {w.objectName()}' for w in QApplication.topLevelWidgets())
        report = f"\nTop-Level Windows:\n{windows}\nTop-Level Widgets:\n{widgets}\n"
        logging.info(report)

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
