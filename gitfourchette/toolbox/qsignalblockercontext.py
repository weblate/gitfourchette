import logging

from gitfourchette.qt import *

logger = logging.getLogger(__name__)


class QSignalBlockerContext:
    """
    Context manager wrapper around QSignalBlocker.
    """

    def __init__(self, *objectsToBlock: QObject | QWidget):
        self.objectsToBlock = objectsToBlock

    def __enter__(self):
        for o in self.objectsToBlock:
            if o.signalsBlocked():  # pragma: no cover
                logger.warning(f"Nesting QSignalBlockerContexts isn't a great idea! {o}")
            o.blockSignals(True)

    def __exit__(self, excType, excValue, excTraceback):
        for o in self.objectsToBlock:
            o.blockSignals(False)
