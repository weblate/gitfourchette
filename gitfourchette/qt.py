# GitFourchette's preferred Qt binding is PyQt6, but it is compatibile with other Qt bindings.
# You can force a specific binding with the QT_API environment variable.
# Values recognized by QT_API:
#       pyqt6       (highly recommended, first-class support)
#       pyqt5       (OK if you can't use Qt 6 yet)
#       pyside6     (OK)
#       pyside2     (avoid this one if possible)
#
# If your preferred binding has trouble running (especially if it's a bit out of date),
# you can try to install "qtpy" (not to be confused with pyqt) and pass the QTPY=1 environment variable.
#
# If you're running unit tests, use the PYTEST_QT_API environment variable instead.

import os
import sys

from gitfourchette.appconsts import *

QT_BINDING_ORDER = ["pyqt6", "pyqt5", "pyside6", "pyside2", "qtpy"]

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
DEVDEBUG = __debug__ and not PYINSTALLER_BUNDLE

if PYINSTALLER_BUNDLE:  # in PyInstaller bundles, target a fixed API
    from ._buildconstants import qtBinding as QT_BINDING_FIXED
    QT_BINDING_ORDER = [QT_BINDING_FIXED]
    qtBindingBootPref = QT_BINDING_ORDER[0]
else:
    qtBindingBootPref = os.environ.get("QT_API", "").lower()

    # If QT_API isn't set, see if the app's prefs file specifies a preferred Qt binding
    if not qtBindingBootPref:
        import json
        prefsPath = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
        prefsPath = os.path.join(prefsPath, "GitFourchette", "prefs.json")
        jsonPrefs = None
        try:
            with open(prefsPath, 'rt', encoding='utf-8') as f:
                jsonPrefs = json.load(f)
            qtBindingBootPref = jsonPrefs.get("debug_forceQtApi", "").lower()
        except (IOError, ValueError):
            pass
        del json, prefsPath, jsonPrefs

    QTPY = os.environ.get("QTPY", "").lower() in ["1", "true", "yes"]

if QTPY:
    from qtpy.QtCore import *
    from qtpy.QtWidgets import *
    from qtpy.QtGui import *
    from qtpy import API_NAME as qtBindingName
    from qtpy.QtCore import __version__ as qtBindingVersion
else:
    if not qtBindingBootPref:
        qtBindingBootPref = QT_BINDING_ORDER[0]
    elif qtBindingBootPref not in QT_BINDING_ORDER:
        # Sanitize value if user passed in junk
        sys.stderr.write(f"Unrecognized Qt binding name: '{qtBindingBootPref}'\n")
        qtBindingBootPref = QT_BINDING_ORDER[0]
    else:
        # Move preferred binding to front of list
        QT_BINDING_ORDER.remove(qtBindingBootPref)
        QT_BINDING_ORDER.insert(0, qtBindingBootPref)

    print("Qt binding order is:", QT_BINDING_ORDER)

    qtBindingName = ""
    for _tentative in QT_BINDING_ORDER:
        assert _tentative.islower()

        try:
            if _tentative == "pyside6":
                from PySide6.QtCore import *
                from PySide6.QtWidgets import *
                from PySide6.QtGui import *
                from PySide6 import __version__ as qtBindingVersion
                qtBindingName = "PySide6"
                QT6 = PYSIDE6 = True

            elif _tentative == "pyqt6":
                from PyQt6.QtCore import *
                from PyQt6.QtWidgets import *
                from PyQt6.QtGui import *
                from PyQt6.QtCore import QT_VERSION_STR as qtBindingVersion
                qtBindingName = "PyQt6"
                QT6 = PYQT6 = True
                Signal = pyqtSignal
                Slot = pyqtSlot

            elif _tentative == "pyqt5":
                from PyQt5.QtCore import *
                from PyQt5.QtWidgets import *
                from PyQt5.QtGui import *
                from PyQt5.QtCore import QT_VERSION_STR as qtBindingVersion
                qtBindingName = "PyQt5"
                QT5 = PYQT5 = True
                Signal = pyqtSignal
                Slot = pyqtSlot

            elif _tentative == "pyside2":
                from PySide2.QtCore import *
                from PySide2.QtWidgets import *
                from PySide2.QtGui import *
                from PySide2 import __version__ as qtBindingVersion
                qtBindingName = "PySide2"
                QT5 = PYSIDE2 = True

            else:
                print("Unsupported binding", _tentative)
                continue

            break

        except ImportError:
            continue

    del _tentative

if not qtBindingName:
    sys.stderr.write("No Qt binding found. Please install either PyQt5, PyQt6, or PySide6.\n")
    sys.exit(1)

# -----------------------------------------------------------------------------
# Set up platform constants

KERNEL = QSysInfo.kernelType().lower()
MACOS = KERNEL == "darwin"
WINDOWS = KERNEL == "winnt"
FREEDESKTOP = (KERNEL == "linux") or ("bsd" in KERNEL)

# -----------------------------------------------------------------------------
# Exclude some known bad PySide6 versions

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

# -----------------------------------------------------------------------------
# Patch some holes in Qt bindings with stuff that qtpy doesn't provide

# QEvent::ThemeChange is still undocumented. It only seems to work in Qt 6.
if PYQT5 or PYQT6:
    QEvent.Type.ThemeChange = 0xD2

# Patch PySide2's exec_ functions
if PYSIDE2:
    def qMenuExec(menu: QMenu, *args, **kwargs):
        menu.exec_(*args, **kwargs)
    QApplication.exec = QApplication.exec_
    QMenu.exec = qMenuExec

# Work around PYSIDE-2234 for PySide2 and PySide6. PySide6 6.5.0+ does implement QRunnable.create,
# but its implementation sometimes causes random QRunnable objects to bubble up to MainWindow.eventFilter
# as the 'event' arg, somehow. So just replace PySide6's implementation.
if PYSIDE2 or PYSIDE6:
    class QRunnableFunctionWrapper(QRunnable):
        def __init__(self, func):
            super().__init__()
            self._func = func
        def run(self):
            self._func()
    QRunnable.create = lambda func: QRunnableFunctionWrapper(func)

# Disable "What's this?" in dialog box title bars (Qt 5 only -- this is off by default in Qt 6)
if QT5:
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_DisableWindowContextHelpButton)

# Try to import QtDBus on Linux (note: PySide2 doesn't have it)
HAS_QTDBUS = False
if FREEDESKTOP and not PYSIDE2:
    if QTPY:
        from qtpy.QtDBus import *
    elif PYSIDE6:
        from PySide6.QtDBus import *
    elif PYQT6:
        from PyQt6.QtDBus import *
    elif PYQT5:
        from PyQt5.QtDBus import *
    else:
        assert False
    HAS_QTDBUS = True


# -----------------------------------------------------------------------------
# Utility functions

def tr(s, *args, **kwargs):
    return QCoreApplication.translate("", s, *args, **kwargs)


def translate(context, s, *args, **kwargs):
    return QCoreApplication.translate(context, s, *args, **kwargs)


def qAppName():
    """ User-facing application name. Shorthand for QApplication.applicationDisplayName(). """
    return QApplication.applicationDisplayName()
