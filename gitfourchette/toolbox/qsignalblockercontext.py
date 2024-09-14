# -----------------------------------------------------------------------------
# Copyright (C) 2024 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

import warnings

from gitfourchette.qt import *


class QSignalBlockerContext:
    """
    Context manager wrapper around QSignalBlocker.
    """

    nestingLevels = {}
    concurrentBlockers = 0

    def __init__(self, *objectsToBlock: QObject | QWidget):
        self.objectsToBlock = objectsToBlock

    def __enter__(self):
        self.concurrentBlockers += 1

        for o in self.objectsToBlock:
            key = id(o)
            self.nestingLevels[key] = self.nestingLevels.get(key, 0) + 1
            if self.nestingLevels[key] == 1:
                # Block signals if we're the first QSignalBlockerContext to refer to this object
                if o.signalsBlocked():  # pragma: no cover
                    warnings.warn(f"QSignalBlockerContext: object signals already blocked! {o}")
                o.blockSignals(True)

    def __exit__(self, excType, excValue, excTraceback):
        for o in self.objectsToBlock:
            key = id(o)
            self.nestingLevels[key] -= 1
            assert self.nestingLevels[key] >= 0
            # Unblock signals if we were holding last remaining reference to this object
            if self.nestingLevels[key] == 0:
                o.blockSignals(False)
                del self.nestingLevels[key]

        self.concurrentBlockers -= 1
        assert self.concurrentBlockers >= 0
        assert self.concurrentBlockers != 0 or not self.concurrentBlockers
