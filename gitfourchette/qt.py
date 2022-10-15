# GitFourchette's preferred Qt binding is PySide6.
# Compatibility with additional Qt bindings is provided through qtpy.
# You can force a specific binding with the QT_API environment variable.
# Values recognized by QT_API:
#       pyside6     (preferred)
#       pyside2
#       pyqt6
#       pyqt5
# If you're running unit tests, use the PYTEST_QT_API environment variable instead.

from qtpy.QtCore import *
from qtpy.QtWidgets import *
from qtpy.QtGui import *
from qtpy import API_NAME as qtBindingName
from qtpy.QtCore import __version__ as qtBindingVersion
