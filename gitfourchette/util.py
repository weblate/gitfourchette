from dataclasses import dataclass
from gitfourchette.qt import *
from gitfourchette.settings import PathDisplayStyle
from pygit2 import Oid
import os
import re
import sys
import traceback
import typing


HOME = os.path.abspath(os.path.expanduser('~'))


_supportedImageFormats = None


def sign(x):
    if x < 0:
        return -1
    elif x > 0:
        return 1
    else:
        return 0


def hasFlag(value, flag):
    return (value & flag) == flag


def fplural(fmt: str, n: int) -> str:
    if n == 1:
        fmt = fmt.replace("#~", "")
    else:
        fmt = fmt.replace("#~", "# ")

    out = fmt.replace("#", str(n))

    if n == 1:
        out = re.sub(r"\^\w+", "", out)
    else:
        out = out.replace("^", "")
    return out


def compactPath(path: str) -> str:
    # Normalize path first, which also turns forward slashes to backslashes on Windows.
    path = os.path.abspath(path)
    if path.startswith(HOME):
        path = "~" + path[len(HOME):]
    return path


def abbreviatePath(path: str, style: PathDisplayStyle = PathDisplayStyle.FULL_PATHS) -> str:
    if style == PathDisplayStyle.ABBREVIATE_DIRECTORIES:
        splitLong = path.split('/')
        for i in range(len(splitLong) - 1):
            if splitLong[i][0] == '.':
                splitLong[i] = splitLong[i][:2]
            else:
                splitLong[i] = splitLong[i][0]
        return '/'.join(splitLong)
    elif style == PathDisplayStyle.SHOW_FILENAME_ONLY:
        return path.rsplit('/', 1)[-1]
    else:
        return path


def shortHash(oid: Oid) -> str:
    from gitfourchette.settings import prefs
    return oid.hex[:prefs.shortHashChars]


def isZeroId(oid: Oid) -> bool:
    return oid.raw == (b'\x00' * 20)


# Ampersands from user strings must be sanitized for QLabel.
def labelQuote(text: str) -> str:
    return F"“{text.replace('&', '&&')}”"


def showInFolder(pathStr):
    """
    Show a file or folder with explorer/finder.
    Source: https://stackoverflow.com/a/46019091/3388962
    """
    path = os.path.abspath(pathStr)
    product = QSysInfo.productType()
    if product == 'windows':
        if not os.path.isdir(path):  # If it's a file, select it within the folder.
            args = ['/select,', path]
        else:
            args = [path]  # If it's a folder, open it.
        if QProcess.startDetached('explorer', args):
            return
    elif product == 'osx':  # TODO: "The returned string will be updated for Qt 6"
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
    QDesktopServices.openUrl(QUrl.fromLocalFile(dirPath))


def messageSummary(body: str):
    messageContinued = False
    message: str = body.strip()
    newline = message.find('\n')
    if newline > -1:
        messageContinued = newline < len(message) - 1
        message = message[:newline]
        if messageContinued:
            message += " [...]"
    return message, messageContinued


def onAppThread():
    appInstance = QApplication.instance()
    return appInstance and appInstance.thread() is QThread.currentThread()


def excMessageBox(
        exc,
        title="Unhandled Exception",
        message="An exception was thrown.",
        parent=None,
        printExc=True,
        showExcSummary=True,
        icon=QMessageBox.Icon.Critical
):
    try:
        if printExc:
            traceback.print_exception(exc.__class__, exc, exc.__traceback__)

        # bail out if we're not running on Qt's application thread
        if not onAppThread():
            sys.stderr.write("excMessageBox: not on application thread; bailing out\n")
            return

        if showExcSummary:
            summary = traceback.format_exception_only(exc.__class__, exc)
            summary = ''.join(summary).strip()
            message += "\n\n" + summary

        def shortenTracebackPath(line):
            return re.sub(r'^\s*File "([^"]+)"',
                          lambda m: F'File "{os.path.basename(m.group(1))}"',
                          line, 1)

        details = traceback.format_exception(exc.__class__, exc, exc.__traceback__)
        details = [shortenTracebackPath(line) for line in details]
        details = ''.join(details).strip()

        qmb = QMessageBox(icon, title, message, parent=parent)
        qmb.setDetailedText(details)

        detailsEdit: QTextEdit = qmb.findChild(QTextEdit)
        if detailsEdit:
            font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
            font.setPointSize(min(font.pointSize(), 8))
            detailsEdit.setFont(font)
            detailsEdit.setMinimumWidth(600)

        qmb.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)  # don't leak dialog

        if parent is not None:
            qmb.setWindowModality(Qt.WindowModality.WindowModal)
            qmb.show()
        else:  # without a parent, .show() won't work
            qmb.exec_()

    except BaseException as excMessageBoxError:
        sys.stderr.write(f"*********************************************\n")
        sys.stderr.write(f"excMessageBox failed!!!\n")
        sys.stderr.write(f"*********************************************\n")
        traceback.print_exception(excMessageBoxError)


def excStrings(exc):
    summary = traceback.format_exception_only(exc.__class__, exc)
    summary = ''.join(summary).strip()

    details = traceback.format_exception(exc.__class__, exc, exc.__traceback__)
    details = ''.join(details).strip()

    return summary, details


@dataclass
class ActionDef:
    caption: str = ""
    callback: typing.Callable = None
    icon: QStyle.StandardPixmap = None
    checkState: int = 0


def quickMenu(
        parent: QWidget,
        actionDefs: list[ActionDef],
        menu: QMenu = None
) -> QMenu:
    actions = []

    for actionDef in actionDefs:
        if not actionDef:
            newAction = QAction(parent)
            newAction.setSeparator(True)
        else:
            newAction = QAction(actionDef.caption, parent)
            newAction.triggered.connect(actionDef.callback)
            if actionDef.icon:
                icon = parent.style().standardIcon(actionDef.icon)
                newAction.setIcon(icon)
            if actionDef.checkState != 0:
                newAction.setCheckable(True)
                newAction.setChecked(actionDef.checkState == 1)

        actions.append(newAction)

    if menu:
        menu.insertSeparator(menu.actions()[0])
        menu.insertActions(menu.actions()[0], actions)
    else:
        menu = QMenu(parent)
        menu.addActions(actions)

    return menu


def addComboBoxItem(comboBox: QComboBox, caption: str, userData=None, isCurrent=False):
    if isCurrent:
        caption = "• " + caption
    index = comboBox.count()
    comboBox.addItem(caption, userData=userData)
    if isCurrent:
        comboBox.setCurrentIndex(index)
    return index


def stockIcon(iconId: QStyle.StandardPixmap | str):
    if type(iconId) is str:
        return QIcon.fromTheme(iconId)
    else:
        return QApplication.style().standardIcon(iconId)


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


def tweakWidgetFont(widget: QWidget, relativeSize: int = 100, bold: bool = False):
    font: QFont = widget.font()
    font.setPointSize(font.pointSize() * relativeSize // 100)
    font.setBold(bold)
    widget.setFont(font)
    return font


class QSignalBlockerContext:
    """
    Context manager wrapper around QSignalBlocker.
    """
    def __init__(self, objectToBlock: QObject):
        self.objectToBlock = objectToBlock

    def __enter__(self):
        self.blocker = QSignalBlocker(self.objectToBlock)

    def __exit__(self, excType, excValue, excTraceback):
        if self.blocker:
            self.blocker.unblock()
            self.blocker = None


class DisableWidgetContext:
    def __init__(self, objectToBlock: QWidget):
        self.objectToBlock = objectToBlock

    def __enter__(self):
        self.objectToBlock.setEnabled(False)

    def __exit__(self, excType, excValue, excTraceback):
        self.objectToBlock.setEnabled(True)


class NonCriticalOperation:
    def __init__(self, operation: str):
        self.operation = operation

    def __enter__(self):
        pass

    def __exit__(self, excType, excValue, excTraceback):
        if excValue:
            excMessageBox(excValue, message=self.operation + " failed.")
            return True  # don't propagate


class PersistentFileDialog:
    @staticmethod
    def getPath(key):
        from gitfourchette import settings
        try:
            return settings.history.fileDialogPaths[key]
        except KeyError:
            return ""

    @staticmethod
    def savePath(key, path):
        if path:
            from gitfourchette import settings
            settings.history.fileDialogPaths[key] = path
            settings.history.write()

    @staticmethod
    def getSaveFileName(parent, caption: str, filter="", selectedFilter=""):
        key = caption
        initialDir = PersistentFileDialog.getPath(key)
        path, selectedFilter = QFileDialog.getSaveFileName(parent, caption, initialDir, filter, selectedFilter)
        PersistentFileDialog.savePath(key, path)
        return path, selectedFilter

    @staticmethod
    def getOpenFileName(parent, caption: str, filter="", selectedFilter=""):
        key = caption
        initialDir = PersistentFileDialog.getPath(key)
        path, selectedFilter = QFileDialog.getOpenFileName(parent, caption, initialDir, filter, selectedFilter)
        PersistentFileDialog.savePath(key, path)
        return path, selectedFilter

    @staticmethod
    def getExistingDirectory(parent, caption: str, options=QFileDialog.Option.ShowDirsOnly):
        key = caption
        initialDir = PersistentFileDialog.getPath(key)
        path = QFileDialog.getExistingDirectory(parent, caption, initialDir, options)
        PersistentFileDialog.savePath(key, path)
        return path
