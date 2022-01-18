from gitfourchette.allqt import *

if qtBindingName == "PyQt5":
    from PyQt5.QtTest import QTest
elif qtBindingName == "PySide2":
    from PySide2.QtTest import QTest
else:
    raise ImportError("Unsupported Qt binding")
