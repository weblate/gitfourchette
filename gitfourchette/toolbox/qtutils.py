import base64
import os
from typing import Callable

from gitfourchette.qt import *

_supportedImageFormats = None
_stockIconCache = {}


MultiShortcut = list[QKeySequence]


def setWindowModal(widget: QWidget, modality: Qt.WindowModality = Qt.WindowModality.WindowModal):
    """
    Sets the WindowModal modality on a widget unless we're in test mode.
    (On macOS, window-modal dialogs trigger an unskippable animation
    that wastes time in unit tests.)
    """

    from gitfourchette.settings import TEST_MODE
    if not TEST_MODE:
        widget.setWindowModality(modality)


def openFolder(path: str):
    QDesktopServices.openUrl(QUrl.fromLocalFile(path))


def showInFolder(path: str):  # pragma: no cover (platform-specific)
    """
    Show a file or folder with explorer/finder.
    Source for Windows & macOS: https://stackoverflow.com/a/46019091/3388962
    """
    path = os.path.abspath(path)
    isdir = os.path.isdir(path)

    if FREEDESKTOP and HAS_QTDBUS:
        # https://www.freedesktop.org/wiki/Specifications/file-manager-interface
        iface = QDBusInterface("org.freedesktop.FileManager1", "/org/freedesktop/FileManager1")
        if iface.isValid():
            if PYQT5 or PYQT6:
                # PyQt5/6 needs the array of strings to be spelled out explicitly.
                stringType = QMetaType.Type.QString
                args = QDBusArgument()
                args.beginArray(stringType if PYQT5 else stringType.value)
                args.add(path)
                args.endArray()
            else:
                # Thankfully, PySide6 is more pythonic here.
                args = [path]
            iface.call("ShowItems", args, "")
            iface.deleteLater()
            return

    elif WINDOWS:
        if not isdir:  # If it's a file, select it within the folder.
            args = ['/select,', path]
        else:
            args = [path]  # If it's a folder, open it.
        if QProcess.startDetached('explorer', args):
            return

    elif MACOS and not isdir:
        args = [
            '-e', 'tell application "Finder"',
            '-e', 'activate',
            '-e', F'select POSIX file "{path}"',
            '-e', 'end tell',
            '-e', 'return'
        ]
        if not QProcess.execute('/usr/bin/osascript', args):
            return

    # Fallback.
    dirPath = path if os.path.isdir(path) else os.path.dirname(path)
    openFolder(dirPath)


def onAppThread():
    appInstance = QApplication.instance()
    return bool(appInstance and appInstance.thread() is QThread.currentThread())


def isImageFormatSupported(filename: str):
    """
    Guesses whether an image is in a supported format from its filename.
    This is for when QImageReader.imageFormat(path) doesn't cut it (e.g. if the file doesn't exist on disk).
    """
    global _supportedImageFormats

    if _supportedImageFormats is None:
        _supportedImageFormats = [str(fmt, 'ascii') for fmt in QImageReader.supportedImageFormats()]

    ext = os.path.splitext(filename)[-1]
    ext = ext.removeprefix(".").lower()

    return ext in _supportedImageFormats


def adjustedWidgetFontSize(widget: QWidget, relativeSize: int = 100):
    return round(widget.font().pointSize() * relativeSize / 100.0)


def tweakWidgetFont(widget: QWidget, relativeSize: int = 100, bold: bool = False):
    font: QFont = widget.font()
    font.setPointSize(round(font.pointSize() * relativeSize / 100.0))
    font.setBold(bold)
    widget.setFont(font)
    return font


def formatWidgetText(widget: QAbstractButton | QLabel, *args, **kwargs):
    text = widget.text()
    text = text.format(*args, **kwargs)
    widget.setText(text)
    return text


def formatWidgetTooltip(widget: QWidget, *args, **kwargs):
    text = widget.toolTip()
    text = text.format(*args, **kwargs)
    widget.setToolTip(text)
    return text


def addComboBoxItem(comboBox: QComboBox, caption: str, userData=None, isCurrent=False):
    if isCurrent:
        caption = "• " + caption
    index = comboBox.count()
    comboBox.addItem(caption, userData=userData)
    if isCurrent:
        comboBox.setCurrentIndex(index)
    return index


def isDarkTheme(palette: QPalette | None = None):
    if palette is None:
        palette = QApplication.palette()
    themeBG = palette.color(QPalette.ColorRole.Base)  # standard theme background color
    themeFG = palette.color(QPalette.ColorRole.Text)  # standard theme foreground color
    return themeBG.value() < themeFG.value()


def stockIcon(iconId: str | QStyle.StandardPixmap) -> QIcon:
    """
    If SVG icons don't show up, you may need to install the 'qt6-svg' package.
    """

    # Special cases
    if (MACOS or WINDOWS) and iconId == "achtung":
        iconId = QStyle.StandardPixmap.SP_MessageBoxWarning

    # Attempt to get cached icon
    if iconId in _stockIconCache:
        return _stockIconCache[iconId]

    def lookUpNamedIcon(name: str) -> QIcon:
        # First, attempt to get a matching icon from the assets
        def assetCandidates():
            prefix = "assets:"
            dark = isDarkTheme()
            for ext in ".svg", ".png":
                if dark:  # attempt to get dark mode variant first
                    yield f"{prefix}{name}@dark{ext}"
                yield f"{prefix}{name}{ext}"

        for candidate in assetCandidates():
            f = QFile(candidate)
            if f.exists():
                return QIcon(f.fileName())

        # Fall back to theme icons
        return QIcon.fromTheme(name)

    if type(iconId) is str:
        icon = lookUpNamedIcon(iconId)
    else:
        icon = QApplication.style().standardIcon(iconId)

    _stockIconCache[iconId] = icon
    return icon


def clearStockIconCache():
    _stockIconCache.clear()


def appendShortcutToToolTipText(tip: str, shortcut: QKeySequence | QKeySequence.StandardKey | Qt.Key, singleLine=True):
    mutedColor = QApplication.palette().toolTipText().color()
    mutedColor.setAlphaF(.6)
    mutedColor = mutedColor.name(QColor.NameFormat.HexArgb)

    if type(shortcut) in [QKeySequence.StandardKey, Qt.Key]:
        shortcut = QKeySequence(shortcut)

    hint = shortcut.toString(QKeySequence.SequenceFormat.NativeText)
    hint = f"<span style='color: {mutedColor}'> &nbsp;{hint}</span>"
    prefix = ""
    if singleLine:
        prefix = "<p style='white-space: pre'>"
    return f"{prefix}{tip} {hint}"


def appendShortcutToToolTip(widget: QWidget, shortcut: QKeySequence | QKeySequence.StandardKey | Qt.Key, singleLine=True):
    tip = widget.toolTip()
    tip = appendShortcutToToolTipText(tip, shortcut, singleLine)
    widget.setToolTip(tip)
    return tip


def itemViewVisibleRowRange(view: QAbstractItemView):
    assert isinstance(view, QListView)
    model = view.model()  # use the view's top-level model to only search filtered rows

    rect = view.viewport().contentsRect()
    top = view.indexAt(rect.topLeft())
    if not top.isValid():
        return range(-1)

    bottom = view.indexAt(rect.bottomLeft())
    if not bottom.isValid():
        bottom = model.index(model.rowCount() - 1, 0)

    return range(top.row(), bottom.row() + 1)


class DisableWidgetContext:
    def __init__(self, objectToBlock: QWidget):
        self.objectToBlock = objectToBlock

    def __enter__(self):
        self.objectToBlock.setEnabled(False)

    def __exit__(self, excType, excValue, excTraceback):
        self.objectToBlock.setEnabled(True)


class DisableWidgetUpdatesContext:
    def __init__(self, widget: QWidget):
        self.widget = widget

    def __enter__(self):
        self.widget.setUpdatesEnabled(False)

    def __exit__(self, excType, excValue, excTraceback):
        self.widget.setUpdatesEnabled(True)

    @staticmethod
    def methodDecorator(func):
        def wrapper(*args, **kwargs):
            widget: QWidget = args[0]
            with DisableWidgetUpdatesContext(widget):
                return func(*args, **kwargs)
        return wrapper


class MakeNonNativeDialog(QObject):  # pragma: no cover (macOS-specific)
    """
    Enables the AA_DontUseNativeDialogs attribute, and disables it when the dialog is shown.
    Meant to be used to disable the iOS-like styling of dialog boxes on modern macOS.
    """
    def __init__(self, parent: QDialog):
        super().__init__(parent)
        nonNativeAlready = QCoreApplication.testAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs)
        if nonNativeAlready:
            self.deleteLater()
            return
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs, True)
        parent.installEventFilter(self)

    def eventFilter(self, watched, event: QEvent):
        if event.type() == QEvent.Type.Show:
            QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs, False)
            watched.removeEventFilter(self)
            self.deleteLater()
        return False


class QScrollBackupContext:
    def __init__(self, *items: QAbstractScrollArea | QScrollBar):
        self.scrollBars = []
        self.values = []

        for o in items:
            if isinstance(o, QAbstractScrollArea):
                self.scrollBars.append(o.horizontalScrollBar())
                self.scrollBars.append(o.verticalScrollBar())
            else:
                assert isinstance(o, QScrollBar)
                self.scrollBars.append(o)

    def __enter__(self):
        self.values = [o.value() for o in self.scrollBars]

    def __exit__(self, exc_type, exc_val, exc_tb):
        for o, v in zip(self.scrollBars, self.values):
            o.setValue(v)


class QTabBarStyleNoRotatedText(QProxyStyle):
    """
    Prevents text from being rotated in a QTabBar's labels with the West or East positions.

    Does not work well with the macOS native theme!
    Does not work at all with PySide2!

    Adapted from https://forum.qt.io/post/433000
    """

    def sizeFromContents(self, type: QStyle.ContentsType, option: QStyleOption, size: QSize, widget: QWidget) -> QSize:
        s = super().sizeFromContents(type, option, size, widget)
        if type == QStyle.ContentsType.CT_TabBarTab:
            s.transpose()
        return s

    def drawControl(self, element: QStyle.ControlElement, option: QStyleOption, painter: QPainter, widget: QWidget = None):
        if element == QStyle.ControlElement.CE_TabBarTabLabel:
            assert isinstance(option, QStyleOptionTab)
            option: QStyleOptionTab = QStyleOptionTab(option)  # copy
            option.shape = QTabBar.Shape.RoundedNorth  # override shape
        super().drawControl(element, option, painter, widget)


class CallbackAccumulator(QTimer):
    def __init__(self, parent: QObject, callback: Callable, delay: int = 0):
        super().__init__(parent)
        self.setObjectName("CallbackAccumulator")
        self.setSingleShot(True)
        self.setInterval(delay)
        self.timeout.connect(callback)

    @staticmethod
    def deferredMethod(callback: Callable):
        attr = f"__callbackaccumulator_{id(callback)}"

        def wrapper(obj):
            try:
                defer = getattr(obj, attr)
            except AttributeError:
                defer = CallbackAccumulator(obj, lambda: callback(obj))
                setattr(obj, attr, defer)
            defer.start()

        return wrapper


def makeInternalLink(urlAuthority: str, urlPath: str = "", urlFragment: str = "", **urlQueryItems) -> str:
    url = QUrl()
    url.setScheme(APP_URL_SCHEME)
    url.setAuthority(urlAuthority)

    if urlPath:
        if not urlPath.startswith("/"):
            urlPath = "/" + urlPath
        url.setPath(urlPath)

    if urlFragment:
        url.setFragment(urlFragment)

    query = QUrlQuery()
    for k, v in urlQueryItems.items():
        query.addQueryItem(k, v)
    if query:
        url.setQuery(query)

    return url.toString()


def makeMultiShortcut(*args) -> MultiShortcut:
    if len(args) == 1 and type(args[0]) is list:
        args = args[0]

    shortcuts = []

    for alt in args:
        t = type(alt)
        if t is str:
            shortcuts.append(QKeySequence(alt))
        elif t is QKeySequence.StandardKey:
            shortcuts.extend(QKeySequence.keyBindings(alt))
        elif t is Qt.Key:  # for PySide2 compat
            shortcuts.append(QKeySequence(alt))
        else:
            assert t is QKeySequence
            shortcuts.append(alt)

    # Ensure no duplicates (stable order since Python 3.7+)
    shortcuts = list(dict.fromkeys(shortcuts))

    return shortcuts


def lerp(v1, v2, cmin, cmax, c):
    p = (c-cmin) / (cmax-cmin)
    p = max(p, 0)
    p = min(p, 1)
    v = v2*p + v1*(1-p)
    return v


class DocumentLinks:
    AUTHORITY = "adhoc"

    def __init__(self):
        self.callbacks = {}

    def new(self, func: Callable[[QObject], None]) -> str:
        key = base64.urlsafe_b64encode(os.urandom(16)).decode("ascii")
        self.callbacks[key] = func
        return makeInternalLink(self.AUTHORITY, urlPath="", urlFragment=key)

    def processLink(self, url: QUrl, invoker: QObject) -> bool:
        if url.scheme() == APP_URL_SCHEME and url.authority() == self.AUTHORITY:
            cb = self.callbacks[url.fragment()]
            cb(invoker)
            return True
        return False
