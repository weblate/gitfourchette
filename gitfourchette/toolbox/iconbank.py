"""
If SVG icons don't show up, you may need to install the 'qt6-svg' package.
"""

from gitfourchette.qt import *
from gitfourchette.toolbox.qtutils import isDarkTheme, writeTempFile

_stockIconCache = {}
_tempSvgFiles = []


def assetCandidates(name: str):
    prefix = "assets:icons/"
    dark = isDarkTheme()
    for ext in ".svg", ".png":
        if dark:  # attempt to get dark mode variant first
            yield QFile(f"{prefix}{name}@dark{ext}")
        yield QFile(f"{prefix}{name}{ext}")


def getBestIconFile(name: str) -> str:
    try:
        f = next(f for f in assetCandidates(name) if f.exists())
        return f.fileName()
    except StopIteration as exc:
        raise KeyError(f"no built-in icon asset '{name}'") from exc


def lookUpNamedIcon(name: str) -> QIcon:
    try:
        # First, attempt to get a matching icon from the assets
        path = getBestIconFile(name)
        return QIcon(path)
    except KeyError:
        pass

    # Fall back to Qt standard icons (with "SP_" prefix)
    if name.startswith("SP_"):
        entry = getattr(QStyle.StandardPixmap, name)
        return QApplication.style().standardIcon(entry)

    # Fall back to theme icon
    return QIcon.fromTheme(name)


def remapSvgColors(name: str, colorRemapTable: str) -> QIcon:
    path = getBestIconFile(name)
    with open(path, encoding="utf-8") as f:
        originalData = f.read()

    data = originalData
    for pair in colorRemapTable.split(";"):
        oldColor, newColor = pair.split("=")
        data = data.replace(oldColor, newColor)

    if data == originalData:
        # No changes, return original icon
        return QIcon(path)

    # Keep the temp file object around so that QIcon can read off it as needed
    tempFile = writeTempFile("icon-XXXXXX.svg", data)
    _tempSvgFiles.append(tempFile)

    icon = QIcon(tempFile.fileName())
    return icon


def stockIcon(iconId: str, colorRemapTable="") -> QIcon:
    # Special cases
    if (MACOS or WINDOWS) and iconId == "achtung":
        iconId = "SP_MessageBoxWarning"

    if colorRemapTable:
        key = f"{iconId}?{colorRemapTable}"
    else:
        key = iconId

    # Attempt to get cached icon
    if key in _stockIconCache:
        return _stockIconCache[key]

    if colorRemapTable:
        try:
            icon = remapSvgColors(iconId, colorRemapTable)
        except KeyError:
            icon = lookUpNamedIcon(iconId)
    else:
        icon = lookUpNamedIcon(iconId)

    # Save icon in cache
    _stockIconCache[key] = icon
    return icon


def clearStockIconCache():
    _stockIconCache.clear()
    _tempSvgFiles.clear()
