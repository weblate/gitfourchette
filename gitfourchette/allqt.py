def getPreferredQtBindingName(fallback="pyside2"):
    import os
    for variable in ["QT_PREFERRED_BINDING", "PYTEST_QT_API"]:
        binding = os.environ.get(variable)
        if binding:
            return binding.lower()
    return fallback


qtBindingName = getPreferredQtBindingName()

if qtBindingName == "pyqt5":
    from PyQt5.QtWidgets import *
    from PyQt5.QtGui import *
    from PyQt5.QtCore import *
    from PyQt5.QtCore import QT_VERSION_STR as qtVersion
    from PyQt5.QtCore import PYQT_VERSION_STR as qtBindingVersion
    from PyQt5.QtCore import pyqtSignal as Signal
    from PyQt5.QtCore import pyqtSlot as Slot
elif qtBindingName == "pyside2":
    from PySide2.QtWidgets import *
    from PySide2.QtGui import *
    from PySide2.QtCore import *
    from PySide2.QtCore import __version__ as qtVersion
    from PySide2 import __version__ as qtBindingVersion
elif qtBindingName == "pyside6":
    from PySide6.QtWidgets import *
    from PySide6.QtGui import *
    from PySide6.QtCore import *
    from PySide6.QtCore import __version__ as qtVersion
    from PySide6 import __version__ as qtBindingVersion
elif qtBindingName == "pyqt6":
    # PyQt6 requires fully qualified enums.
    raise ImportError("PyQt6 isn't supported yet. You can use PySide6 instead.")
else:
    raise ImportError(F"Unknown Qt binding {qtBindingName}.")
