from gitfourchette.qt import *
from gitfourchette import log


class QSignalBlockerContext:
    """
    Context manager wrapper around QSignalBlocker.
    """

    def __init__(self, *objectsToBlock: QObject | QWidget):
        self.objectsToBlock = objectsToBlock

    def __enter__(self):
        for o in self.objectsToBlock:
            if o.signalsBlocked():
                log.warning("QSignalBlockerContext", "Nesting QSignalBlockerContexts isn't a great idea!")
            o.blockSignals(True)

    def __exit__(self, excType, excValue, excTraceback):
        for o in self.objectsToBlock:
            o.blockSignals(False)
