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
    PatchPurpose,
    simplifyOctalFileMode,
    splitRemoteUrl,
    stripRemoteUrlPath,
)
from .memoryindicator import MemoryIndicator
from .messageboxes import (
    MessageBoxIconName, excMessageBox, asyncMessageBox,
    showWarning, showInformation, askConfirmation, NonCriticalOperation)
from .iconbank import stockIcon, clearStockIconCache
from .pathutils import PathDisplayStyle, abbreviatePath, compactPath
from .persistentfiledialog import PersistentFileDialog
from .qbusyspinner import QBusySpinner
from .qcomboboxwithpreview import QComboBoxWithPreview
from .qelidedlabel import QElidedLabel
from .qfilepickercheckbox import QFilePickerCheckBox
from .qsignalblockercontext import QSignalBlockerContext
from .qstatusbar2 import QStatusBar2
from .qtabwidget2 import QTabWidget2, QTabBar2
from .qtutils import (
    addComboBoxItem, setWindowModal, isImageFormatSupported,
    onAppThread,
    adjustedWidgetFontSize,
    tweakWidgetFont,
    formatWidgetText,
    formatWidgetTooltip,
    itemViewVisibleRowRange,
    isDarkTheme,
    mutedTextColorHex,
    mutedToolTipColorHex,
    appendShortcutToToolTipText,
    appendShortcutToToolTip,
    openFolder, showInFolder,
    DisableWidgetContext,
    DisableWidgetUpdatesContext,
    QScrollBackupContext, QTabBarStyleNoRotatedText,
    makeInternalLink,
    MultiShortcut, makeMultiShortcut,
    CallbackAccumulator,
    lerp,
    DocumentLinks,
)
from .textutils import (
    escape, escamp, paragraphs, messageSummary, elide,
    toTightUL, toRoomyUL, linkify,
    clipboardStatusMessage,
    hquo, hquoe, bquo, bquoe, lquo, lquoe, tquo, tquoe,
    btag,
)
from .validatormultiplexer import ValidatorMultiplexer
