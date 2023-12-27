import os

# Keep qtpy binding (used by main app) in sync with pytest
if os.environ.get("PYTEST_QT_API") and os.environ.get("QT_API"):
    # PYTEST_QT_API takes precedence over QT_API
    os.environ["QT_API"] = os.environ["PYTEST_QT_API"]
elif os.environ.get("QT_API"):
    os.environ["PYTEST_QT_API"] = os.environ["QT_API"]
else:
    from pytestqt.qt_compat import qt_api
    os.environ["PYTEST_QT_API"] = qt_api.pytest_qt_api
    os.environ["QT_API"] = qt_api.pytest_qt_api

# Force qtpy to honor QT_API
os.environ["FORCE_QT_API"] = "1"

from gitfourchette.qt import *
from qtpy.QtTest import QTest

from gitfourchette import log
log.setVerbosity(log.logger.Verbosity.VERBOSE)
