from PySide2.QtCore import QObject, Signal


class GlobalStatusSignalContainer(QObject):
    statusText = Signal(str)
    progressValue = Signal(int)
    progressMaximum = Signal(int)
    progressDisable = Signal()

    def setText(self, arg):
        print("[status]", arg)
        self.statusText.emit(arg)

    def setProgressMaximum(self, v):
        self.progressMaximum.emit(v)

    def setProgressValue(self, v):
        self.progressValue.emit(v)

    def clearProgress(self):
        self.progressDisable.emit()


gstatus = GlobalStatusSignalContainer()

