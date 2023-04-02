from gitfourchette.qt import *
from typing import Callable


class QRunnableFunctionWrapper(QRunnable):
    """
    QRunnable.create(...) isn't available in PySide2/PySide6 (5.15.8/6.4.2).
    """

    def __init__(self, function: Callable, autoDelete: bool = True):
        super().__init__()
        self._run = function
        self.setAutoDelete(autoDelete)

    def run(self):
        self._run()
