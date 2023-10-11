# GitFourchette's preferred Qt binding is PySide6.
#
# PySide6 is strongly recommended, but compatibility with other Qt bindings is provided through qtpy.
# If qtpy is installed, you can force a specific binding with the QT_API environment variable.
# Values recognized by QT_API:
#       pyside6     (highly recommended, first-class support)
#       pyqt6       (OK)
#       pyqt5       (OK if you can't use Qt 6)
#       pyside2     (avoid this one if possible)
#
# If you're running unit tests, use the PYTEST_QT_API environment variable instead.

import os
import sys

from gitfourchette.appconsts import *

QTPY = False
QT5 = False
QT6 = False
PYSIDE2 = False
PYSIDE6 = False
PYQT5 = False
PYQT6 = False
MACOS = False
WINDOWS = False
PYINSTALLER_BUNDLE = (getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'))

# If PySide6 is installed, we'll import it directly.
# If PySide6 is missing, we'll use qtpy.
# Only use qtpy as a last resort because it tries to pull in QtOpenGL and other bloat.

# Decide whether to use qtpy and import it if needed.
if not PYINSTALLER_BUNDLE:  # in PyInstaller bundles, we're guaranteed to have PySide6
    forcedQtApi = os.environ.get("QT_API", "").lower()
    QTPY = "pyside6" != forcedQtApi

    # Bypass qtpy if we have PySide6 and the user isn't forcing QT_API
    if not forcedQtApi:
        try:
            from PySide6 import __version__ as bogus
            del bogus
            QTPY = False
        except ImportError:
            pass

    # No dice, we have to use qtpy.
    if QTPY:
        try:
            from qtpy.QtCore import *
            from qtpy.QtWidgets import *
            from qtpy.QtGui import *
            from qtpy import API_NAME as qtBindingName
            from qtpy.QtCore import __version__ as qtBindingVersion
        except ImportError:
            assert forcedQtApi in ["", "pyside6"], \
                "To use any Qt binding other than PySide6, please install qtpy. Or, unset QT_API to use PySide6."
            QTPY = False

    del forcedQtApi

# Import PySide6 if we've determined that we can.
if not QTPY:
    from PySide6.QtCore import *
    from PySide6.QtWidgets import *
    from PySide6.QtGui import *
    from PySide6 import __version__ as qtBindingVersion
    qtBindingName = "PySide6"
    QT6 = PYSIDE6 = True

MACOS = QSysInfo.productType() in ["osx", "macos"]  # "osx": Qt5 legacy
WINDOWS = QSysInfo.productType() in ["windows"]
FREEDESKTOP = not MACOS and not WINDOWS

if PYSIDE2:  # Patch PySide2's exec_ functions
    def qMenuExec(menu: QMenu, *args, **kwargs):
        menu.exec_(*args, **kwargs)
    QApplication.exec = QApplication.exec_
    QMenu.exec = qMenuExec

if PYSIDE6:
    badPyside6Versions = [
        "6.4.0",  # PYSIDE-2104
        "6.4.0.1",  # PYSIDE-2104
        "6.5.1",  # PYSIDE-2346
    ]
    if any(v == qtBindingVersion for v in badPyside6Versions):
        QApplication()
        QMessageBox.critical(None, "", f"PySide6 version {qtBindingVersion} isn't supported.\n"
                                       f"Please upgrade to the latest version of PySide6.")
        exit(1)

# QEvent::ThemeChange is still undocumented. It only seems to work in Qt 6.
if PYQT5 or PYQT6:
    QEvent.Type.ThemeChange = 0xD2

# Disable "What's this?" in dialog box title bars (Qt 5 only -- this is off by default in Qt 6)
if QT5:
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_DisableWindowContextHelpButton)

# Try to import QtDBus on Linux (note: PySide2 doesn't have it)
HAS_QTDBUS = False
if FREEDESKTOP and not PYSIDE2:
    if QTPY:
        from qtpy.QtDBus import *
    else:
        from PySide6.QtDBus import *
    HAS_QTDBUS = True


def tr(s, *args, **kwargs):
    return QCoreApplication.translate("", s, *args, **kwargs)


def translate(context, s, *args, **kwargs):
    return QCoreApplication.translate(context, s, *args, **kwargs)


def qAppName():
    """ User-facing application name. Shorthand for QApplication.applicationDisplayName(). """
    return QApplication.applicationDisplayName()
