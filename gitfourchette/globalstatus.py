from gitfourchette import log
from gitfourchette.qt import QObject, Signal


class GlobalStatusSignalContainer(QObject):
    statusText = Signal(str)
    progressValue = Signal(int)
    progressMaximum = Signal(int)
    progressDisable = Signal()

    def setText(self, arg):
        log.info("status", arg)
        self.statusText.emit(arg)

    def setProgressMaximum(self, v):
        self.progressMaximum.emit(v)

    def setProgressValue(self, v):
        self.progressValue.emit(v)

    def clearProgress(self):
        self.progressDisable.emit()

    def setIndeterminateProgressCaption(self, arg):
        self.progressMaximum.emit(0)
        self.progressValue.emit(0)
        self.statusText.emit(arg)
        log.info("status", arg)

    def clearIndeterminateProgressCaption(self):
        self.progressDisable.emit()
        self.statusText.emit(None)


globalstatus = GlobalStatusSignalContainer()

