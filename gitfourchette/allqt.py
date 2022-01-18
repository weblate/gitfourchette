qtBindingName = "PySide2"

if qtBindingName == "PyQt5":
    from PyQt5.QtWidgets import *
    from PyQt5.QtGui import *
    from PyQt5.QtCore import *
    from PyQt5.QtCore import QT_VERSION_STR as qtVersion
    from PyQt5.QtCore import PYQT_VERSION_STR as qtBindingVersion
    from PyQt5.QtCore import pyqtSignal as Signal
    from PyQt5.QtCore import pyqtSlot as Slot
elif qtBindingName == "PySide2":
    from PySide2.QtWidgets import *
    from PySide2.QtGui import *
    from PySide2.QtCore import *
    from PySide2.QtCore import __version__ as qtVersion
    from PySide2 import __version__ as qtBindingVersion
else:
    raise ImportError(F"Unsupported Qt binding {qtBindingName}")
