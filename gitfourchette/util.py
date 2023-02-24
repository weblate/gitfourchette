from gitfourchette.qt import *
from gitfourchette.settings import PathDisplayStyle
from pygit2 import Oid
import html
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
def escamp(text: str) -> str:
    return text.replace('&', '&&')


def paragraphs(*args) -> str:
    return "<p>" + "</p><p>".join(args) + "</p>"


def showInFolder(pathStr):
    """
    Show a file or folder with explorer/finder.
    Source: https://stackoverflow.com/a/46019091/3388962
    """
    path = os.path.abspath(pathStr)
    isdir = os.path.isdir(path)

    if WINDOWS:
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


def setWindowModal(widget: QWidget, modality: Qt.WindowModality = Qt.WindowModality.WindowModal):
    """
    Sets the WindowModal modality on a widget unless we're in test mode.
    (On macOS, window-modal dialogs trigger an unskippable animation
    that wastes time in unit tests.)
    """

    from gitfourchette.settings import TEST_MODE
    if not TEST_MODE:
        widget.setWindowModality(modality)


def excMessageBox(
        exc,
        title="",
        message="",
        parent=None,
        printExc=True,
        showExcSummary=True,
        icon: str = 'critical'
):
    try:
        if printExc:
            traceback.print_exception(exc.__class__, exc, exc.__traceback__)

        # bail out if we're not running on Qt's application thread
        if not onAppThread():
            sys.stderr.write("excMessageBox: not on application thread; bailing out\n")
            return

        if not title:
            title = tr("Unhandled exception")
        if not message:
            message = tr("An exception was raised.")

        if showExcSummary:
            summary = traceback.format_exception_only(exc.__class__, exc)
            summary = ''.join(summary).strip()
            message += "<br><br>" + html.escape(summary)

        def shortenTracebackPath(line):
            return re.sub(r'^\s*File "([^"]+)"',
                          lambda m: F'File "{os.path.basename(m.group(1))}"',
                          line, 1)

        details = traceback.format_exception(exc.__class__, exc, exc.__traceback__)
        details = [shortenTracebackPath(line) for line in details]
        details = ''.join(details).strip()

        qmb = asyncMessageBox(parent, icon, title, message)
        qmb.setDetailedText(details)

        detailsEdit: QTextEdit = qmb.findChild(QTextEdit)
        if detailsEdit:
            font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
            font.setPointSize(min(font.pointSize(), 8))
            detailsEdit.setFont(font)
            detailsEdit.setMinimumWidth(600)

        qmb.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)  # don't leak dialog

        if parent is not None:
            setWindowModal(qmb)
            qmb.show()
        else:  # without a parent, .show() won't work
            qmb.exec()

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


def asyncMessageBox(
        parent: QWidget,
        icon: typing.Literal['warning', 'information', 'question', 'critical'],
        title: str,
        text: str,
        buttons=QMessageBox.StandardButton.NoButton,
        macShowTitle=True
) -> QMessageBox:

    icons = {
        'warning': QMessageBox.Icon.Warning,
        'information': QMessageBox.Icon.Information,
        'question': QMessageBox.Icon.Question,
        'critical': QMessageBox.Icon.Critical,
    }

    # macOS doesn't have a titlebar for message boxes, so put the title in the text
    if macShowTitle and MACOS:
        text = "<p><b>" + title + "</b></p>" + text

    qmb = QMessageBox(
        icons.get(icon, QMessageBox.Icon.NoIcon),
        title,
        text,
        buttons,
        parent=parent
    )

    # On macOS (since Big Sur?), all QMessageBox text is bold by default
    if MACOS:
        qmb.setStyleSheet("QMessageBox QLabel { font-weight: normal; }")

    setWindowModal(qmb)
    qmb.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

    return qmb


def showWarning(parent: QWidget, title: str, text: str) -> QMessageBox:
    qmb = asyncMessageBox(parent, 'warning', title, text)
    qmb.show()
    return qmb


def showInformation(parent: QWidget, title: str, text: str) -> QMessageBox:
    qmb = asyncMessageBox(parent, 'information', title, text)
    qmb.show()
    return qmb


def askConfirmation(
        parent: QWidget,
        title: str,
        text: str,
        callback: typing.Callable | Slot | None = None,
        buttons=QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
        okButtonText: str = "",
        okButtonIcon: QIcon | None = None,
        show=True
) -> QMessageBox:

    # Using QMessageBox.StandardButton.Ok instead of QMessageBox.StandardButton.Discard
    # so it connects to the "accepted" signal.
    qmb = asyncMessageBox(parent, 'question', title, text, buttons)

    okButton = qmb.button(QMessageBox.StandardButton.Ok)
    if okButton:
        if okButtonText:
            okButton.setText(okButtonText)
        if okButtonIcon:
            okButton.setIcon(okButtonIcon)

    if callback:
        qmb.accepted.connect(callback)

    if show:
        qmb.show()

    return qmb


def addComboBoxItem(comboBox: QComboBox, caption: str, userData=None, isCurrent=False):
    if isCurrent:
        caption = "• " + caption
    index = comboBox.count()
    comboBox.addItem(caption, userData=userData)
    if isCurrent:
        comboBox.setCurrentIndex(index)
    return index


def stockIcon(iconId: QStyle.StandardPixmap | str | None) -> QIcon:
    if iconId is None:
        return QIcon()
    elif type(iconId) is str:
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
            excMessageBox(excValue, message=tr("Operation failed: {0}.").format(html.escape(self.operation)))
            return True  # don't propagate


class QRunnableFunctionWrapper(QRunnable):
    """
    QRunnable.create(...) isn't available in PySide2/PySide6 (5.15.8/6.4.2).
    """

    def __init__(self, function: typing.Callable, autoDelete: bool = True):
        super().__init__()
        self._run = function
        self.setAutoDelete(autoDelete)

    def run(self):
        self._run()


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
    def getSaveFileName(parent, caption: str, initialFilename="", filter="", selectedFilter=""):
        key = caption

        previousSavePath = PersistentFileDialog.getPath(key)
        if not previousSavePath:
            initialPath = initialFilename
        else:
            previousSaveDir = os.path.dirname(previousSavePath)
            initialPath = os.path.join(previousSaveDir, initialFilename)

        path, selectedFilter = QFileDialog.getSaveFileName(parent, caption, initialPath, filter, selectedFilter)
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
