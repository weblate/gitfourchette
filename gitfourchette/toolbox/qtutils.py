# -----------------------------------------------------------------------------
# Copyright (C) 2024 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

import base64
import itertools
import os
from collections.abc import Callable

from gitfourchette.qt import *

_supportedImageFormats = None

QModelIndex_default = QModelIndex()
QPoint_zero = QPoint()

MultiShortcut = list[QKeySequence]


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
                if PYQT5:
                    stringType = QMetaType.Type.QString
                else:
                    stringType = QMetaType.Type.QString.value
                dbusArgs = QDBusArgument()
                dbusArgs.beginArray(stringType)
                dbusArgs.add(path)
                dbusArgs.endArray()
            else:
                # Thankfully, PySide6 is more pythonic here.
                dbusArgs = [path]
            iface.call("ShowItems", dbusArgs, "")
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
        _supportedImageFormats = [str(fmt.data(), 'ascii') for fmt in QImageReader.supportedImageFormats()]

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


def mutedTextColorHex(w: QWidget, alpha=.5) -> str:
    mutedColor = QApplication.palette().windowText().color()
    mutedColor.setAlphaF(alpha)
    return mutedColor.name(QColor.NameFormat.HexArgb)


def mutedToolTipColorHex() -> str:
    mutedColor = QApplication.palette().toolTipText().color()
    mutedColor.setAlphaF(.6)
    return mutedColor.name(QColor.NameFormat.HexArgb)


def appendShortcutToToolTipText(tip: str, shortcut: QKeySequence | QKeySequence.StandardKey | Qt.Key | str, singleLine=True):
    if isinstance(shortcut, QKeySequence.StandardKey | Qt.Key | str):
        shortcut = QKeySequence(shortcut)

    hint = shortcut.toString(QKeySequence.SequenceFormat.NativeText)
    hint = f"<span style='color: {mutedToolTipColorHex()}'> &nbsp;{hint}</span>"
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
        self.scrollBars: list[QScrollBar] = []
        self.values: list[int] = []

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
        for o, v in zip(self.scrollBars, self.values, strict=True):
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

    def drawControl(self, element: QStyle.ControlElement, option: QStyleOption, painter: QPainter, widget: QWidget | None = None):
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
    if len(args) == 1 and isinstance(args[0], list):
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


def keyEventMatchesMultiShortcut(event: QKeyEvent, shortcuts: MultiShortcut) -> bool:
    modifiers = event.modifiers() if PYQT5 else event.modifiers().value
    eventKS = QKeySequence(modifiers | event.key())
    return eventKS in shortcuts


def lerp(v1, v2, c=.5, cmin=0, cmax=1):
    p = (c-cmin) / (cmax-cmin)
    p = max(p, 0)
    p = min(p, 1)
    v = v2*p + v1*(1-p)
    return v


def writeTempFile(namePattern: str, data: bytes | str) -> QTemporaryFile:
    assert "XXX" in namePattern
    tempFile = QTemporaryFile(os.path.join(qTempDir(), namePattern))
    tempFile.open(QFile.OpenModeFlag.WriteOnly)
    if isinstance(data, str):
        data = data.encode('utf-8')
    tempFile.write(data)
    tempFile.close()
    tempFile.setAutoRemove(True)
    return tempFile


def waitForSignal(parent: QObject | QWidget, signal: SignalInstance):
    loop = QEventLoop(parent)
    signal.connect(lambda: loop.quit())
    loop.exec()
    loop.deleteLater()


def findParentWidget(o: QObject) -> QWidget:
    p = o.parent()
    while p:
        if isinstance(p, QWidget):
            return p
        p = p.parent()
    raise ValueError(f"No parent widget found for {repr(o)}")


def setTabOrder(*args: QWidget):
    """
    Qt 6.6 introduces QWidget::setTabOrder(std::initializer_list<QWidget *> widgets)
    but neither PySide6 nor PyQt6 expose it yet.
    """
    for widget1, widget2 in itertools.pairwise(args):
        QWidget.setTabOrder(widget1, widget2)


class DocumentLinks:
    """
    Bundle of ad-hoc links bound to callback functions.
    """

    AUTHORITY = "adhoc"

    def __init__(self):
        self.callbacks = {}

    def new(self, func: Callable[[QObject], None]) -> str:
        key = base64.urlsafe_b64encode(os.urandom(16)).decode("ascii")
        self.callbacks[key] = func
        return makeInternalLink(self.AUTHORITY, urlPath="", urlFragment=key)

    def processLink(self, url: QUrl | str, invoker: QObject) -> bool:
        if isinstance(url, str):
            url = QUrl(url)
        if url.scheme() == APP_URL_SCHEME and url.authority() == self.AUTHORITY:
            cb = self.callbacks[url.fragment()]
            cb(invoker)
            return True
        return False
