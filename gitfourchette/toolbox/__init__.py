"""
Library of widgets and utilities that aren't specifically tied to GitFourchette's core functionality.
"""

from .actiondef import ActionDef
from .autohidemenubar import AutoHideMenuBar
from .benchmark import Benchmark, benchmark
from .excutils import shortenTracebackPath, excStrings
from .gitutils import (
    shortHash, dumpTempBlob, nameValidationMessage,
    AuthorDisplayStyle, abbreviatePerson,
    simplifyOctalFileMode,
)
from .memoryindicator import MemoryIndicator
from .messageboxes import (
    MessageBoxIconName, excMessageBox, asyncMessageBox,
    showWarning, showInformation, askConfirmation, NonCriticalOperation)
from .pathutils import PathDisplayStyle, abbreviatePath, compactPath
from .persistentfiledialog import PersistentFileDialog
from .qbusyspinner import QBusySpinner
from .qcomboboxwithpreview import QComboBoxWithPreview
from .qelidedlabel import QElidedLabel
from .qsignalblockercontext import QSignalBlockerContext
from .qstatusbar2 import QStatusBar2
from .qtabwidget2 import QTabWidget2, QTabBar2
from .qtutils import (
    addComboBoxItem, setWindowModal, isImageFormatSupported,
    onAppThread, tweakWidgetFont, formatWidgetText,
    formatWidgetTooltip,
    isDarkTheme,
    stockIcon, clearStockIconCache,
    appendShortcutToToolTipText,
    appendShortcutToToolTip,
    openFolder, showInFolder, DisableWidgetContext,
    QScrollBackupContext, QTabBarStyleNoRotatedText,
    makeInternalLink,
    MultiShortcut, makeMultiShortcut,
    CallbackAccumulator,
)
from .textutils import (
    escape, escamp, paragraphs, messageSummary, elide, ulList,
    clipboardStatusMessage,
    hquo, hquoe, bquo, bquoe, lquo, lquoe, tquo, tquoe
)
from .validatormultiplexer import ValidatorMultiplexer
