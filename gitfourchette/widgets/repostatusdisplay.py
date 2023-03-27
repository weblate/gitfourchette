from gitfourchette.qt import *
from gitfourchette.toolbox.qbusyspinner import QBusySpinner


class RepoStatusDisplayCache(QObject):
    updated = Signal(object)

    def __init__(self, parent):
        super().__init__(parent)
        self.status = ""
        self.spinning = False
        self.warning = ""

    def setStatus(self, text: str = "", spinning: bool = False):
        self.status = text
        self.spinning = spinning
        self.fireUpdate()

    def setWarning(self, text: str = ""):
        self.warning = text
        self.fireUpdate()

    def fireUpdate(self):
        self.updated.emit(self)


class RepoStatusDisplay(QWidget):
    def __init__(self, parent):
        super().__init__(parent)

        self.setObjectName("RepoStatusDisplay")

        self.currentStatusDisplayCache = None

        self.statusSpinner = QBusySpinner(self, centerOnParent=False)
        self.statusSpinner.stop()

        self.statusLabel = QLabel()

        self.statusWarning = QLabel()
        self.statusWarning.setStyleSheet("QLabel { background-color: yellow; padding-left: 6px; padding-right: 6px; }")
        self.statusWarning.setHidden(True)

        layout = QHBoxLayout()
        self.setLayout(layout)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.statusSpinner)
        layout.addWidget(self.statusLabel, 1)
        layout.addWidget(self.statusWarning)

    def detach(self):
        if self.currentStatusDisplayCache:
            self.currentStatusDisplayCache.updated.disconnect(self.setContents)
            self.currentStatusDisplayCache.destroyed.disconnect(self.onCacheDestroyed)
        self.currentStatusDisplayCache = None

    def onCacheDestroyed(self):
        self.currentStatusDisplayCache = None

    def install(self, statusDisplayCache: RepoStatusDisplayCache):
        self.detach()
        self.currentStatusDisplayCache = statusDisplayCache
        statusDisplayCache.updated.connect(self.setContents)
        statusDisplayCache.destroyed.connect(self.onCacheDestroyed)
        self.setContents(statusDisplayCache)

    def setContents(self, statusDisplayCache: RepoStatusDisplayCache):
        self.statusLabel.setText(statusDisplayCache.status)
        if statusDisplayCache.spinning:
            self.statusSpinner.start()
        else:
            self.statusSpinner.stop()
        if statusDisplayCache.warning:
            self.statusWarning.setText(statusDisplayCache.warning)
            self.statusWarning.setHidden(False)
        else:
            self.statusWarning.setHidden(True)

    #def paintEvent(self, event:QPaintEvent):
    #    if self.memoryIndicator:
    #        self.updateMemoryIndicator()
    #    super().paintEvent(event)
