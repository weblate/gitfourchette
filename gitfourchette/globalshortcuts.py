from gitfourchette.qt import *

assert QApplication.instance(), "QApplication must have been created before instantiating QKeySequence"


def _makeShortcuts(*args) -> list[QKeySequence]:
    shortcuts = []

    for alt in args:
        if isinstance(alt, str):
            shortcuts.append(QKeySequence(alt))
        elif isinstance(alt, QKeySequence.StandardKey):
            shortcuts.extend(QKeySequence.keyBindings(alt))
        else:
            assert isinstance(alt, QKeySequence)
            shortcuts.append(alt)

    # Ensure no duplicates (stable order since Python 3.7+)
    if qtBindingName == "PySide2":  # QKeySequence isn't hashable in PySide2
        shortcuts = list(dict((str(s), s) for s in shortcuts).values())
    else:
        shortcuts = list(dict.fromkeys(shortcuts))

    return shortcuts


refresh = _makeShortcuts(QKeySequence.StandardKey.Refresh, "Ctrl+R", "F5")
newBranch = _makeShortcuts("Ctrl+B")
pushBranch = _makeShortcuts("Ctrl+P")
pullBranch = _makeShortcuts("Ctrl+Shift+P")
closeTab = _makeShortcuts(QKeySequence.StandardKey.Close)
openRepoFolder = _makeShortcuts("Ctrl+Shift+O")
newStash = _makeShortcuts(QKeySequence.StandardKey.SaveAs, "Ctrl+Shift+S")

stageHotkeys = [Qt.Key.Key_Enter, Qt.Key.Key_Return]  # Enter = on keypad; Return = main keys
discardHotkeys = [Qt.Key.Key_Delete, Qt.Key.Key_Backspace]

