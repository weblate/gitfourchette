from gitfourchette.qt import *

MultiShortcut = list[QKeySequence]


def _makeShortcuts(*args) -> MultiShortcut:
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
    if PYSIDE2:  # QKeySequence isn't hashable in PySide2
        shortcuts = list(dict((str(s), s) for s in shortcuts).values())
    else:
        shortcuts = list(dict.fromkeys(shortcuts))

    return shortcuts


class GlobalShortcuts:
    NO_SHORTCUT = []

    copy: MultiShortcut = NO_SHORTCUT
    refresh: MultiShortcut = NO_SHORTCUT
    newBranch: MultiShortcut = NO_SHORTCUT
    pushBranch: MultiShortcut = NO_SHORTCUT
    pullBranch: MultiShortcut = NO_SHORTCUT
    closeTab: MultiShortcut = NO_SHORTCUT
    openRepoFolder: MultiShortcut = NO_SHORTCUT
    newStash: MultiShortcut = NO_SHORTCUT
    commit: MultiShortcut = NO_SHORTCUT
    amendCommit: MultiShortcut = NO_SHORTCUT
    navBack: MultiShortcut = NO_SHORTCUT
    navForward: MultiShortcut = NO_SHORTCUT

    stageHotkeys = [Qt.Key.Key_Return, Qt.Key.Key_Enter]  # Return: main keys; Enter: on keypad
    discardHotkeys = [Qt.Key.Key_Delete, Qt.Key.Key_Backspace]
    checkoutCommitFromGraphHotkeys = [Qt.Key.Key_Return, Qt.Key.Key_Enter]
    getCommitInfoHotkeys = [Qt.Key.Key_Space]

    @classmethod
    def initialize(cls):
        assert QApplication.instance(), "QApplication must have been created before instantiating QKeySequence"
        cls.copy = _makeShortcuts(QKeySequence.StandardKey.Copy)
        cls.refresh = _makeShortcuts(QKeySequence.StandardKey.Refresh, "Ctrl+R", "F5")
        cls.newBranch = _makeShortcuts("Ctrl+B")
        cls.pushBranch = _makeShortcuts("Ctrl+P")
        cls.pullBranch = _makeShortcuts("Ctrl+Shift+P")
        cls.closeTab = _makeShortcuts(QKeySequence.StandardKey.Close)
        cls.openRepoFolder = _makeShortcuts("Ctrl+Shift+O")
        cls.newStash = _makeShortcuts(QKeySequence.StandardKey.SaveAs, "Ctrl+Shift+S")
        cls.commit = _makeShortcuts("Ctrl+K")
        cls.amendCommit = _makeShortcuts("Ctrl+Shift+K")

        if MACOS:
            cls.navBack = _makeShortcuts("Ctrl+Left")
            cls.navForward = _makeShortcuts("Ctrl+Right")
        else:
            cls.navBack = _makeShortcuts("Alt+Left")
            cls.navForward = _makeShortcuts("Alt+Right")
