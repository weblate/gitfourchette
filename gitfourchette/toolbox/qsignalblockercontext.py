import warnings

from gitfourchette.qt import *


class QSignalBlockerContext:
    """
    Context manager wrapper around QSignalBlocker.
    """

    def __init__(self, *objectsToBlock: QObject | QWidget, skipAlreadyBlocked=False):
        self.objectsToBlock = objectsToBlock
        if skipAlreadyBlocked:
            self.objectsToBlock = [o for o in objectsToBlock if not o.signalsBlocked()]

    def __enter__(self):
        for o in self.objectsToBlock:
            if o.signalsBlocked():  # pragma: no cover
                warnings.warn(f"Nesting QSignalBlockerContexts isn't a great idea! {o}")
            o.blockSignals(True)

    def __exit__(self, excType, excValue, excTraceback):
        for o in self.objectsToBlock:
            o.blockSignals(False)
