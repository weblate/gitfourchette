from gitfourchette.qt import *
_supportedImageFormats = None


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


def tweakWidgetFont(widget: QWidget, relativeSize: int = 100, bold: bool = False):
    font: QFont = widget.font()
    font.setPointSize(font.pointSize() * relativeSize // 100)
    font.setBold(bold)
    widget.setFont(font)
    return font


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


class DisableWidgetContext:
    def __init__(self, objectToBlock: QWidget):
        self.objectToBlock = objectToBlock

    def __enter__(self):
        self.objectToBlock.setEnabled(False)

    def __exit__(self, excType, excValue, excTraceback):
        self.objectToBlock.setEnabled(True)
