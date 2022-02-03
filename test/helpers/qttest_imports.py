from gitfourchette.allqt import *

if qtBindingName == "pyqt5":
    from PyQt5.QtTest import QTest
elif qtBindingName == "pyside2":
    from PySide2.QtTest import QTest
elif qtBindingName == "pyside6":
    from PySide6.QtTest import QTest
else:
    raise ImportError("Unsupported Qt binding")
