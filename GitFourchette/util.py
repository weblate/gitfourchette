import re
from pathlib import Path
from PySide2.QtCore import *
from PySide2.QtGui import *


def fplural(fmt: str, n: int) -> str:
    out = fmt.replace("#", str(n))
    if n == 1:
        out = re.sub(r"\^\w+", "", out)
    else:
        out = out.replace("^", "")
    return out


def compactSystemPath(path: str) -> str:
    home = str(Path.home())
    if path.startswith(str(home)):
        path = "~" + path[len(home):]
    return path


def compactRepoPath(path: str) -> str:
    splitLong = path.split('/')
    for i in range(len(splitLong) - 1):
        if splitLong[i][0] == '.':
            splitLong[i] = splitLong[i][:2]
        else:
            splitLong[i] = splitLong[i][0]
    return '/'.join(splitLong)


def showInFolder(pathStr):
    """
    Show a file or folder with explorer/finder.
    Source: https://stackoverflow.com/a/46019091/3388962
    """
    path = Path(pathStr).absolute()
    product = QSysInfo.productType()
    if product == 'windows':
        if path.is_dir():
            args = ['/select,', str(path)]
        else:
            args = [str(path)]
        if QProcess.startDetached('explorer', args):
            return
    elif product == 'osx':  # TODO: "The returned string will be updated for Qt 6"
        args = [
            '-e', 'tell application "Finder"',
            '-e', 'activate',
            '-e', F'select POSIX file "{str(path)}"',
            '-e', 'end tell',
            '-e', 'return'
        ]
        if not QProcess.execute('/usr/bin/osascript', args):
            return
    # Fallback.
    dirPath = path if path.is_dir() else path.parent
    QDesktopServices.openUrl(QUrl(str(dirPath)))

