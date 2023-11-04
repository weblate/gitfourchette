"""
Library of widgets and utilities that aren't specifically tied to GitFourchette's core functionality.
"""

from .actiondef import ActionDef
from .autohidemenubar import AutoHideMenuBar
from .customtabwidget import CustomTabWidget, CustomTabBar
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
from .qrunnablefunctionwrapper import QRunnableFunctionWrapper
from .qsignalblockercontext import QSignalBlockerContext
from .qstatusbar2 import QStatusBar2
from .qtutils import (
    addComboBoxItem, setWindowModal, isImageFormatSupported,
    onAppThread, tweakWidgetFont, formatWidgetText,
    formatWidgetTooltip,
    isDarkTheme,
    stockIcon, clearStockIconCache,
    appendShortcutToToolTip,
    openFolder, showInFolder, DisableWidgetContext,
    QScrollBackupContext, QTabBarStyleNoRotatedText,
    makeInternalLink,
    reformatQLabel,
    MultiShortcut, makeMultiShortcut
)
from .textutils import escape, escamp, paragraphs, messageSummary, elide
from .validatormultiplexer import ValidatorMultiplexer
