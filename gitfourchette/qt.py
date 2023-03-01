# GitFourchette's preferred Qt binding is PySide6.
# Compatibility with additional Qt bindings is provided through qtpy.
# You can force a specific binding with the QT_API environment variable.
# Values recognized by QT_API:
#       pyside6     (recommended, first-class support)
#       pyqt6       (OK)
#       pyqt5       (OK if you can't use Qt 6)
#       pyside2     (avoid this one if possible)
# If you're running unit tests, use the PYTEST_QT_API environment variable instead.

import os
import sys

QT5 = False
QT6 = False
PYSIDE2 = False
PYSIDE6 = False
PYQT5 = False
PYQT6 = False
MACOS = False
WINDOWS = False
PYINSTALLER_BUNDLE = (getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'))

if PYINSTALLER_BUNDLE or "pyside6" == os.environ.get("QT_API", "").lower():
    # If we're making a PyInstaller build, qtpy will try to pull in QtOpenGL and other bloat.
    # So, bypass qtpy and import PySide6 manually.
    from PySide6.QtCore import *
    from PySide6.QtWidgets import *
    from PySide6.QtGui import *
    from PySide6 import __version__ as qtBindingVersion
    qtBindingName = "PySide6"
    QT6 = PYSIDE6 = True
else:
    from qtpy.QtCore import *
    from qtpy.QtWidgets import *
    from qtpy.QtGui import *
    from qtpy import API_NAME as qtBindingName
    from qtpy.QtCore import __version__ as qtBindingVersion
    from qtpy import QT5, QT6, PYSIDE2, PYSIDE6, PYQT5, PYQT6

    if PYSIDE2 or PYSIDE6:
        from qtpy import PYSIDE_VERSION as qtBindingVersion
    else:
        from qtpy import PYQT_VERSION as qtBindingVersion


MACOS = QSysInfo.productType() in ["osx", "macos"]  # "osx": Qt5 legacy
WINDOWS = QSysInfo.productType() in ["windows"]

if PYSIDE2:  # Patch PySide2's exec_ functions
    def qMenuExec(menu: QMenu, *args, **kwargs):
        menu.exec_(*args, **kwargs)
    QApplication.exec = QApplication.exec_
    QMenu.exec = qMenuExec

if PYSIDE6 and qtBindingVersion.startswith("6.4.0"):  # See PYSIDE-2104
    QApplication()
    QMessageBox.critical(None, "", "PySide6 6.4.0 isn't supported. Please upgrade to 6.4.1 or later.")
    exit(1)


# Disable "What's this?" in dialog box title bars (Qt 5 only -- this is off by default in Qt 6)
if QT5:
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_DisableWindowContextHelpButton)


def tr(s, *args, **kwargs):
    return QCoreApplication.translate("", s, *args, **kwargs)


def translate(context, s, *args, **kwargs):
    return QCoreApplication.translate(context, s, *args, **kwargs)


def qAppName():
    """ User-facing application name. Shorthand for QApplication.applicationDisplayName(). """
    return QApplication.applicationDisplayName()
