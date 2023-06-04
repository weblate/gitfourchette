from gitfourchette.qt import *
from gitfourchette.porcelain import NameValidationError


def translateExceptionName(exc: BaseException):
    t = {
        "ConnectionRefusedError": translate("Exception", "Connection refused"),
        "FileNotFoundError": translate("Exception", "File not found"),
    }
    name = type(exc).__name__
    return t.get(name, name)


def translateNameValidationCode(code: int):
    E = NameValidationError
    t = {
        E.ILLEGAL_NAME: translate("NameValidationError", "Illegal name."),
        E.ILLEGAL_SUFFIX: translate("NameValidationError", "Illegal suffix."),
        E.ILLEGAL_PREFIX: translate("NameValidationError", "Illegal prefix."),
        E.CONTAINS_ILLEGAL_SEQ: translate("NameValidationError", "Contains illegal character sequence."),
        E.CONTAINS_ILLEGAL_CHAR: translate("NameValidationError", "Contains illegal character."),
        E.CANNOT_BE_EMPTY: translate("NameValidationError", "Cannot be empty."),
        E.NOT_WINDOWS_FRIENDLY: translate("NameValidationError", "This name is discouraged for compatibility with Windows."),
        E.NAME_TAKEN: translate("NameValidationError", "This name is already taken."),
    }
    return t.get(code, "Name validation error {0}".format(code))


def prefsTranslationTable():
    return {
        "general": translate("Prefs", "General"),
        "diff": translate("Prefs", "Diff"),
        "tabs": translate("Prefs", "Tabs"),
        "graph": translate("Prefs", "Graph"),
        "trash": translate("Prefs", "Trash"),
        "external": translate("Prefs", "External tools"),
        "debug": translate("Prefs", "Debug"),

        "language": translate("Prefs", "Language"),
        "qtStyle": translate("Prefs", "Theme"),
        "shortHashChars": (translate("Prefs", "Shorten hashes to"), translate("Prefs", "characters")),
        "shortTimeFormat": translate("Prefs", "Short time format"),
        "pathDisplayStyle": translate("Prefs", "Path display style"),
        "authorDisplayStyle": translate("Prefs", "Author display style"),
        "maxRecentRepos": translate("Prefs", "Max recent repos"),
        "showStatusBar": translate("Prefs", "Show status bar"),
        "autoHideMenuBar": translate("Prefs", "Toggle menu bar visibility with Alt key"),

        "diff_font": translate("Prefs", "Font"),
        "diff_tabSpaces": (translate("Prefs", "One tab is"), translate("Prefs", "spaces")),
        "diff_largeFileThresholdKB": (translate("Prefs", "Max diff size"), translate("Prefs", "KB")),
        "diff_imageFileThresholdKB": (translate("Prefs", "Max image size"), translate("Prefs", "KB")),
        "diff_wordWrap": translate("Prefs", "Word wrap"),
        "diff_showStrayCRs": translate("Prefs", "Highlight stray “CR” characters"),
        "diff_colorblindFriendlyColors": translate("Prefs", "Colorblind-friendly color scheme"),

        "tabs_closeButton": translate("Prefs", "Show tab close button"),
        "tabs_expanding": translate("Prefs", "Tab bar takes all available width"),
        "tabs_autoHide": translate("Prefs", "Auto-hide tab bar if there’s just 1 tab"),
        "tabs_doubleClickOpensFolder": translate("Prefs", "Double-click a tab to open repo folder"),

        "graph_chronologicalOrder": translate("Prefs", "Commit order"),
        "graph_flattenLanes": translate("Prefs", "Flatten lanes"),
        "graph_rowHeight": translate("Prefs", "Row spacing"),

        "trash_maxFiles": (translate("Prefs", "Max discarded patches in the trash"), translate("Prefs", "files")),
        "trash_maxFileSizeKB": (translate("Prefs", "Don’t salvage patches bigger than"), translate("Prefs", "KB")),
        "trash_HEADER": translate(
            "Prefs",
            "When you discard changes from the working directory, {app} keeps a temporary copy in a hidden "
            "“trash” folder. This gives you a last resort to rescue changes that you have discarded by mistake. "
            "You can look around this trash folder via <i>“Repo &rarr; Rescue Discarded Changes”</i>."),

        "debug_showMemoryIndicator": translate("Prefs", "Show memory indicator in status bar"),
        "debug_showPID": translate("Prefs", "Show technical info in title bar"),
        "debug_verbosity": translate("Prefs", "Logging verbosity"),
        "debug_hideStashJunkParents": translate("Prefs", "Hide synthetic parents of stash commits"),
        "debug_fixU2029InClipboard": translate("Prefs", "Fix U+2029 in text copied from diff editor"),
        "debug_autoRefresh": translate("Prefs", "Auto-refresh when app regains focus"),

        "external_editor": translate("Prefs", "Text editor"),
        "external_diff": translate("Prefs", "Diff tool"),
        "external_merge": translate("Prefs", "Merge tool"),

        "FULL_PATHS": translate("PathDisplayStyle", "Full paths"),
        "ABBREVIATE_DIRECTORIES": translate("PathDisplayStyle", "Abbreviate directories"),
        "SHOW_FILENAME_ONLY": translate("PathDisplayStyle", "Show filename only"),

        "FULL_NAME": translate("Prefs", "Full name"),
        "FIRST_NAME": translate("Prefs", "First name"),
        "LAST_NAME": translate("Prefs", "Last name"),
        "INITIALS": translate("Prefs", "Initials"),
        "FULL_EMAIL": translate("Prefs", "Full email"),
        "ABBREVIATED_EMAIL": translate("Prefs", "Abbreviated email"),

        "CRAMPED": translate("Prefs", "Cramped"),
        "TIGHT": translate("Prefs", "Tight"),
        "RELAXED": translate("Prefs", "Relaxed"),
        "ROOMY": translate("Prefs", "Roomy"),
        "SPACIOUS": translate("Prefs", "Spacious"),
    }
