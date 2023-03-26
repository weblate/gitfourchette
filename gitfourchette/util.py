from dataclasses import dataclass
from gitfourchette import porcelain
from gitfourchette.qt import *
from gitfourchette.settings import PathDisplayStyle
from gitfourchette import log
from gitfourchette import tempdir
from pygit2 import Oid
import contextlib
import html
import os
import pygit2
import re
import shlex
import sys
import traceback
import typing


HOME = os.path.abspath(os.path.expanduser('~'))

MessageBoxIconName = typing.Literal['warning', 'information', 'question', 'critical']

_supportedImageFormats = None

_generalFontMetrics = QFontMetrics(QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont))


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


def shortHash(oid: pygit2.Oid) -> str:
    from gitfourchette.settings import prefs
    return oid.hex[:prefs.shortHashChars]


def isZeroId(oid: pygit2.Oid) -> bool:
    return oid.raw == (b'\x00' * 20)


# Ampersands from user strings must be sanitized for QLabel.
def escamp(text: str) -> str:
    return text.replace('&', '&&')


def paragraphs(*args) -> str:
    """
    Surrounds each argument string with an HTML "P" tag
    and returns the concatenated P tags.
    """

    # If passed an actual list object, use that as the argument list.
    if len(args) == 1 and type(args[0]) == list:
        args = args[0]

    return "<p>" + "</p><p>".join(args) + "</p>"


def openFolder(path: str):
    QDesktopServices.openUrl(QUrl.fromLocalFile(path))


def showInFolder(path: str):
    """
    Show a file or folder with explorer/finder.
    Source: https://stackoverflow.com/a/46019091/3388962
    """
    path = os.path.abspath(path)
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
    openFolder(dirPath)


def openInExternalTool(
        parent: QWidget,
        prefKey: str,
        paths: list[str],
        allowQDesktopFallback: bool = False):

    from gitfourchette import settings

    command = getattr(settings.prefs, prefKey, "").strip()

    if not command and allowQDesktopFallback:
        for p in paths:
            QDesktopServices.openUrl(QUrl.fromLocalFile(p))
        return

    if not command:
        translatedPrefKey = prefKey  # TODO: access PrefsDialog.settingsTranslationTable
        showWarning(
            parent,
            translatedPrefKey,
            translate("Global", "Please set up “{0}” in the Preferences.").format(translatedPrefKey))
        return

    tokens = shlex.split(command, posix=not WINDOWS)

    for i, path in enumerate(paths, start=1):
        placeholderIndex = tokens.index(f"${i}")
        if path:
            tokens[placeholderIndex] = path
        else:
            del tokens[placeholderIndex]

    # Little trick to prevent opendiff (launcher shim for Xcode's FileMerge) from exiting immediately.
    # (Just launching /bin/bash -c ... doesn't make it wait)
    if os.path.basename(tokens[0]) == "opendiff":
        #tokens = ["/bin/bash", "-c", f"""'{tokens[0]}' "$@" | cat""", "--"] + tokens[1:]
        scriptPath = os.path.join(tempdir.getSessionTemporaryDirectory(), "opendiff.sh")
        with open(scriptPath, "w") as scriptFile:
            scriptFile.write(f"""#!/bin/sh\nset -e\n'{tokens[0]}' "$@" | cat""")
        os.chmod(scriptPath, 0o700)  # should be 500
        tokens = ["/bin/sh", scriptPath] + tokens[1:]

    print("Starting process:", " ".join(tokens))

    p = QProcess(parent)
    p.setProgram(tokens[0])
    p.setArguments(tokens[1:])
    p.setWorkingDirectory(os.path.dirname(paths[0]))
    p.setProcessChannelMode(QProcess.ProcessChannelMode.ForwardedChannels)
    p.finished.connect(lambda code, status: print("Process done:", code, status))
    p.start(mode=QProcess.OpenModeFlag.Unbuffered)

    if p.state() == QProcess.ProcessState.NotRunning:
        print("Failed to start?")

    waitToStart = p.waitForStarted(msecs=10000)
    if not waitToStart:
        print("Failed to start?")

    return p


def openInTextEditor(parent: QWidget, path: str):
    return openInExternalTool(parent, "external_editor", [path], allowQDesktopFallback=True)


def openInDiffTool(parent: QWidget, a: str, b: str):
    return openInExternalTool(parent, "external_diff", [a, b])


def openInMergeTool(parent: QWidget, ancestor: str, ours: str, theirs: str, output: str):
    return openInExternalTool(parent, "external_merge", [ancestor, ours, theirs, output])


def dumpTempBlob(
        repo: pygit2.Repository,
        dir: str,
        entry: pygit2.DiffFile | pygit2.IndexEntry | None,
        inBrackets: str):

    # In merge conflicts, the IndexEntry may be None (for the ancestor, etc.)
    if not entry:
        return ""

    blobId = entry.id
    blob: pygit2.Blob = repo[blobId].peel(pygit2.Blob)
    name, ext = os.path.splitext(os.path.basename(entry.path))
    name = F"[{inBrackets}]{name}{ext}"
    path = os.path.join(dir, name)
    with open(path, "wb") as f:
        f.write(blob.data)
    return path


def messageSummary(body: str, elision=" […]"):
    messageContinued = False
    message: str = body.strip()
    newline = message.find('\n')
    if newline > -1:
        messageContinued = newline < len(message) - 1
        message = message[:newline]
        if messageContinued:
            message += elision
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


def translateExceptionName(exc: BaseException):
    d = {
        "ConnectionRefusedError": translate("Exception", "Connection refused"),
        "FileNotFoundError": translate("Exception", "File not found"),
    }
    name = type(exc).__name__
    return d.get(name, name)


def excMessageBox(
        exc,
        title="",
        message="",
        parent=None,
        printExc=True,
        showExcSummary=True,
        icon: MessageBoxIconName = 'critical'
):
    try:
        if printExc:
            traceback.print_exception(exc.__class__, exc, exc.__traceback__)

        # Without a parent, show() won't work. Try to find a QMainWindow to use as the parent.
        if not parent:
            for tlw in QApplication.topLevelWidgets():
                if isinstance(tlw, QMainWindow):
                    parent = tlw
                    break

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

        # Keep user from triggering more exceptions by clicking on stuff in the background
        qmb.setWindowModality(Qt.WindowModality.ApplicationModal)

        if parent:
            qmb.show()
        else:
            # Without a parent, show() won't work. So, use exec() as the very last resort.
            # (Calling exec() may crash on macOS if another modal dialog is active.)
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
        icon: MessageBoxIconName,
        title: str,
        text: str,
        buttons=QMessageBox.StandardButton.NoButton,
        macShowTitle=True,
        deleteOnClose=True,
) -> QMessageBox:

    loggedMessage = F"[{title}] " + html.unescape(re.sub(r"<[^<]+?>", " ", text))
    if icon in ['information', 'question']:
        log.info("MessageBox", loggedMessage)
    else:
        log.warning("MessageBox", loggedMessage)

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

    if parent:
        setWindowModal(qmb)

    if deleteOnClose:
        qmb.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

    return qmb


def showWarning(parent: QWidget, title: str, text: str) -> QMessageBox:
    """
    Shows a warning message box asynchronously.
    """
    qmb = asyncMessageBox(parent, 'warning', title, text)
    qmb.show()
    return qmb


def showInformation(parent: QWidget, title: str, text: str) -> QMessageBox:
    """
    Shows an information message box asynchronously.
    """
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
        show=True,
        messageBoxIcon: MessageBoxIconName = "question",
) -> QMessageBox:
    """
    Shows a confirmation message box asynchronously.

    If you override `buttons`, be careful with your choice of StandardButton values;
    some of them won't emit the `accepted` signal which is connected to the callback.
    """

    qmb = asyncMessageBox(parent, messageBoxIcon, title, text, buttons)

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


def translateNameValidationError(e: porcelain.NameValidationError):
    E = porcelain.NameValidationError
    errorDescriptions = {
        E.ILLEGAL_NAME: translate("NameValidationError", "Illegal name."),
        E.ILLEGAL_SUFFIX: translate("NameValidationError", "Illegal suffix."),
        E.ILLEGAL_PREFIX: translate("NameValidationError", "Illegal prefix."),
        E.CONTAINS_ILLEGAL_SEQ: translate("NameValidationError", "Contains illegal character sequence."),
        E.CONTAINS_ILLEGAL_CHAR: translate("NameValidationError", "Contains illegal character."),
        E.CANNOT_BE_EMPTY: translate("NameValidationError", "Cannot be empty."),
        E.NOT_WINDOWS_FRIENDLY: translate("NameValidationError", "This name is discouraged for compatibility with Windows."),
    }
    return errorDescriptions.get(e.code, "Name validation error {0}".format(e.code))


def validateRefName(name: str, reservedNames: list[str], nameTakenMessage: str = "") -> str:
    try:
        porcelain.validateRefName(name)
    except porcelain.NameValidationError as exc:
        return translateNameValidationError(exc)

    if name.lower() in (n.lower() for n in reservedNames):
        if not nameTakenMessage:
            nameTakenMessage = translate("NameValidationError", "This name is already taken.")
        return nameTakenMessage

    return ""  # validation passed, no error


def elide(text: str, ems: int = 20):
    maxWidth = _generalFontMetrics.horizontalAdvance(ems * 'M')
    return _generalFontMetrics.elidedText(text, Qt.TextElideMode.ElideMiddle, maxWidth)


class QSignalBlockerContext:
    """
    Context manager wrapper around QSignalBlocker.
    """
    def __init__(self, *objectsToBlock: QObject | QWidget):
        self.objectsToBlock = objectsToBlock

    def __enter__(self):
        for o in self.objectsToBlock:
            if o.signalsBlocked():
                log.warning("QSignalBlockerContext", "Nesting QSignalBlockerContexts isn't a great idea!")
            o.blockSignals(True)

    def __exit__(self, excType, excValue, excTraceback):
        for o in self.objectsToBlock:
            o.blockSignals(False)


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
    def getPath(key: str, fallbackPath: str = ""):
        from gitfourchette import settings
        return settings.history.fileDialogPaths.get(key, fallbackPath)

    @staticmethod
    def savePath(key, path):
        if path:
            from gitfourchette import settings
            settings.history.fileDialogPaths[key] = path
            settings.history.write()

    @staticmethod
    def saveFile(parent: QWidget, key: str, caption: str, initialFilename="", filter="", selectedFilter="", deleteOnClose=True):
        previousSavePath = PersistentFileDialog.getPath(key)
        if not previousSavePath:
            initialPath = initialFilename
        else:
            previousSaveDir = os.path.dirname(previousSavePath)
            initialPath = os.path.join(previousSaveDir, initialFilename)

        qfd = QFileDialog(parent, caption, initialPath, filter)
        qfd.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        qfd.setFileMode(QFileDialog.FileMode.AnyFile)
        if selectedFilter:
            qfd.selectNameFilter(selectedFilter)

        qfd.fileSelected.connect(lambda path: PersistentFileDialog.savePath(key, path))

        if deleteOnClose:
            qfd.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        setWindowModal(qfd)
        return qfd

    @staticmethod
    def openFile(parent: QWidget, key: str, caption: str, filter="", selectedFilter="", fallbackPath="", deleteOnClose=True):
        initialDir = PersistentFileDialog.getPath(key, fallbackPath)

        qfd = QFileDialog(parent, caption, initialDir, filter)
        qfd.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
        qfd.setFileMode(QFileDialog.FileMode.AnyFile)
        if selectedFilter:
            qfd.selectNameFilter(selectedFilter)

        qfd.fileSelected.connect(lambda path: PersistentFileDialog.savePath(key, path))

        if deleteOnClose:
            qfd.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        setWindowModal(qfd)
        return qfd

    @staticmethod
    def openDirectory(parent: QWidget, key: str, caption: str, options=QFileDialog.Option.ShowDirsOnly, deleteOnClose=True):
        initialDir = PersistentFileDialog.getPath(key)

        qfd = QFileDialog(parent, caption, initialDir)
        qfd.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
        qfd.setFileMode(QFileDialog.FileMode.Directory)
        qfd.setOptions(options)

        qfd.fileSelected.connect(lambda path: PersistentFileDialog.savePath(key, path))

        if deleteOnClose:
            qfd.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        setWindowModal(qfd)
        return qfd
