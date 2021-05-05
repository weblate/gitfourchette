from allqt import *
import os
import re
import traceback


HOME = os.path.abspath(os.path.expanduser('~'))


def sign(x):
    if x < 0:
        return -1
    elif x > 0:
        return 1
    else:
        return 0


def bisect(a, x, lo=0, hi=None, key=lambda x: x):
    assert lo >= 0, "low must be non-negative"
    hi = hi or len(a)
    while lo < hi:
        mid = (lo+hi)//2
        if x < key(a[mid]):
            hi = mid
        else:
            lo = mid+1
    return lo


def hasFlag(value, flag):
    return (value & flag) == flag


def fplural(fmt: str, n: int) -> str:
    out = fmt.replace("#", str(n))
    if n == 1:
        out = re.sub(r"\^\w+", "", out)
    else:
        out = out.replace("^", "")
    return out


def compactSystemPath(path: str) -> str:
    # Normalize path first, which also turns forward slashes to backslashes on Windows.
    path = os.path.abspath(path)
    if path.startswith(HOME):
        path = "~" + path[len(HOME):]
    return path


def compactRepoPath(path: str) -> str:
    splitLong = path.split('/')
    for i in range(len(splitLong) - 1):
        if splitLong[i][0] == '.':
            splitLong[i] = splitLong[i][:2]
        else:
            splitLong[i] = splitLong[i][0]
    return '/'.join(splitLong)


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
    QDesktopServices.openUrl(QUrl(dirPath))


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


def excMessageBox(exc, title="Unhandled Exception", message="An exception was thrown.", parent=None):
    traceback.print_exc()

    summary = traceback.format_exception_only(exc.__class__, exc)
    summary = ''.join(summary).strip()

    details = traceback.format_exception(exc.__class__, exc, exc.__traceback__)
    details = ''.join(details).strip()

    qmb = QMessageBox(QMessageBox.Critical, title, F"{message}\n{summary}", parent=parent)
    qmb.setDetailedText(details)

    horizontalSpacer = QSpacerItem(500, 0, QSizePolicy.Minimum, QSizePolicy.Expanding)
    layout = qmb.layout()
    layout.addItem(horizontalSpacer, layout.rowCount(), 0, 1, layout.columnCount())

    qmb.exec_()


def excStrings(exc):
    summary = traceback.format_exception_only(exc.__class__, exc)
    summary = ''.join(summary).strip()

    details = traceback.format_exception(exc.__class__, exc, exc.__traceback__)
    details = ''.join(details).strip()

    return summary, details


def textInputDialog(
        parent: QWidget,
        title: str,
        label: str,
        text: str,
        okButtonText: str = None):
    dlg = QInputDialog(parent)

    dlg.setInputMode(QInputDialog.TextInput)
    dlg.setWindowTitle(title)
    if label:
        dlg.setLabelText(label)
    if text:
        dlg.setTextValue(text)
    if okButtonText:
        dlg.setOkButtonText(okButtonText)

    # This size isn't guaranteed. But it'll expand the dialog horizontally if the label is shorter.
    dlg.resize(400, 128)

    rc = dlg.exec_()

    text = dlg.textValue()
    dlg.deleteLater()  # avoid leaking dialog (can't use WA_DeleteOnClose because we needed to retrieve the message)
    return text, rc == QDialog.DialogCode.Accepted
