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
DEVDEBUG = __debug__ and not PYINSTALLER_BUNDLE

# If PySide6 is installed, we'll import it directly.
# If PySide6 is missing, we'll use qtpy.
# Only use qtpy as a last resort because it tries to pull in QtOpenGL and other bloat.

# Decide whether to use qtpy and import it if needed.
qtBindingBootPref = ""
if not PYINSTALLER_BUNDLE:  # in PyInstaller bundles, we're guaranteed to have PySide6
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

    # Sanitize value so that qtpy doesn't crash if user passed in junk
    if qtBindingBootPref not in ["pyqt5", "pyqt6", "pyside2", "pyside6", ""]:
        sys.stderr.write(f"Unrecognized Qt binding name: '{qtBindingBootPref}'\n")
        qtBindingBootPref = ""

    # Our code targets PySide6 natively, so we need qtpy for all other bindings
    QTPY = "pyside6" != qtBindingBootPref

    # Bypass qtpy if we have PySide6 and the user isn't forcing QT_API
    if not qtBindingBootPref:
        try:
            # Attempt to import PySide6
            from PySide6 import __version__ as bogus
            del bogus
            QTPY = False
        except ImportError:
            # Importing PySide6 didn't work, we'll have to use qtpy
            pass

    # No dice, we have to use qtpy.
    if QTPY:
        # Make sure we forward the desired Qt api to qtpy
        os.environ["QT_API"] = qtBindingBootPref

        try:
            from qtpy.QtCore import *
            from qtpy.QtWidgets import *
            from qtpy.QtGui import *
            from qtpy import API_NAME as qtBindingName
            from qtpy.QtCore import __version__ as qtBindingVersion
        except ImportError:
            assert qtBindingBootPref in ["", "pyside6"], \
                "To use any Qt binding other than PySide6, please install qtpy. Or, unset QT_API to use PySide6."
            QTPY = False

# Import PySide6 directly if we've determined that we can.
if not QTPY:
    from PySide6.QtCore import *
    from PySide6.QtWidgets import *
    from PySide6.QtGui import *
    from PySide6 import __version__ as qtBindingVersion
    qtBindingName = "PySide6"
    QT6 = PYSIDE6 = True

# Set up platform constants
MACOS = QSysInfo.productType().lower() in ["osx", "macos"]  # "osx": Qt5 legacy
WINDOWS = QSysInfo.productType().lower() in ["windows"]
FREEDESKTOP = not MACOS and not WINDOWS

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
    else:
        from PySide6.QtDBus import *
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
