# GitFourchette's preferred Qt binding is PySide6.
# Compatibility with additional Qt bindings is provided through qtpy.
# You can force a specific binding with the QT_API environment variable.
# Values recognized by QT_API:
#       pyside6     (preferred)
#       pyside2
#       pyqt6
#       pyqt5
# If you're running unit tests, use the PYTEST_QT_API environment variable instead.

import os

if "pyside6" == os.environ.get("QT_API", "").lower():
    # If we're making a PyInstaller build, qtpy will try to pull in QtOpenGL and other bloat.
    # So, bypass qtpy and import PySide6 manually.
    from PySide6.QtCore import *
    from PySide6.QtWidgets import *
    from PySide6.QtGui import *
    from PySide6 import __version__ as qtBindingVersion
    qtBindingName = "PySide6"
else:
    from qtpy.QtCore import *
    from qtpy.QtWidgets import *
    from qtpy.QtGui import *
    from qtpy import API_NAME as qtBindingName
    from qtpy.QtCore import __version__ as qtBindingVersion


def tr(s, *args, **kwargs):
    return QCoreApplication.translate("", s, *args, **kwargs)


def translate(context, s, *args, **kwargs):
    return QCoreApplication.translate(context, s, *args, **kwargs)
