import os

if not os.environ.get("PYTEST_QT_API"):
    from pytestqt.qt_compat import qt_api
    os.environ["PYTEST_QT_API"] = qt_api.pytest_qt_api

from gitfourchette.qt import *

if qtBindingName == "pyqt5":
    from PyQt5.QtTest import QTest
elif qtBindingName == "pyside2":
    from PySide2.QtTest import QTest
elif qtBindingName == "pyside6":
    from PySide6.QtTest import QTest
else:
    raise ImportError("Unsupported Qt binding")
