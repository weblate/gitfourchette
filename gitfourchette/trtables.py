from __future__ import annotations
from typing import TYPE_CHECKING

from gitfourchette.porcelain import *
from gitfourchette.qt import translate

if TYPE_CHECKING:
    from gitfourchette.toolbox import PatchPurpose


class TrTables:
    _exceptionNames = {}
    _nameValidationCodes = {}
    _sidebarItems = {}
    _sidebarModes = {}
    _prefKeys = {}
    _diffStatusChars = {}
    _fileModes = {}
    _shortFileModes = {}
    _patchPurposes = {}
    _conflictHelp = {}

    @classmethod
    def init(cls):
        if not cls._exceptionNames:
            cls.retranslateAll()

    @classmethod
    def retranslateAll(cls):
        cls._exceptionNames = cls._init_exceptionNames()
        cls._nameValidationCodes = cls._init_nameValidationCodes()
        cls._sidebarItems = cls._init_sidebarItems()
        cls._sidebarModes = cls._init_sidebarModes()
        cls._prefKeys = cls._init_prefKeys()
        cls._diffStatusChars = cls._init_diffStatusChars()
        cls._fileModes = cls._init_fileModes()
        cls._shortFileModes = cls._init_shortFileModes()
        cls._patchPurposes = cls._init_patchPurposes()
        cls._conflictHelp = cls._init_conflictHelp()

    @classmethod
    def exceptionName(cls, exc: BaseException):
        name = type(exc).__name__
        return cls._exceptionNames.get(name, name)

    @classmethod
    def refNameValidation(cls, code: int):
        try:
            return cls._nameValidationCodes[code]
        except KeyError:
            return translate("NameValidationError", "Name validation error {0}").format(code)

    @classmethod
    def sidebarItem(cls, item: int):
        try:
            return cls._sidebarItems[item]
        except KeyError:
            return "?"+str(item)

    @classmethod
    def sidebarMode(cls, item: int):
        return cls._sidebarModes.get(item, "?")

    @classmethod
    def prefKey(cls, key: str):
        return cls._prefKeys.get(key, key)

    @classmethod
    def prefKeyNoDefault(cls, key: str):
        return cls._prefKeys.get(key, "")

    @classmethod
    def diffStatusChar(cls, c: str):
        return cls._diffStatusChars.get(c, c)

    @classmethod
    def fileMode(cls, m: FileMode):
        try:
            return cls._fileModes[m]
        except KeyError:
            return f"{m:o}"

    @classmethod
    def shortFileModes(cls, m: FileMode):
        try:
            return cls._shortFileModes[m]
        except KeyError:
            return f"{m:o}"

    @classmethod
    def patchPurpose(cls, purpose: PatchPurpose):
        return cls._patchPurposes.get(purpose, "???")

    @classmethod
    def conflictHelp(cls, key: str):
        return cls._conflictHelp.get(key, "?"+key)

    @staticmethod
    def _init_exceptionNames():
        return {
            "ConnectionRefusedError": translate("Exception", "Connection refused"),
            "FileNotFoundError": translate("Exception", "File not found"),
            "PermissionError": translate("Exception", "Permission denied"),
            "GitError": translate("Exception", "Git error"),
        }

    @staticmethod
    def _init_nameValidationCodes():
        from gitfourchette.porcelain import NameValidationError as E
        return {
            E.ILLEGAL_NAME: translate("NameValidationError", "Illegal name."),
            E.ILLEGAL_SUFFIX: translate("NameValidationError", "Illegal suffix."),
            E.ILLEGAL_PREFIX: translate("NameValidationError", "Illegal prefix."),
            E.CONTAINS_ILLEGAL_SEQ: translate("NameValidationError", "Contains illegal character sequence."),
            E.CONTAINS_ILLEGAL_CHAR: translate("NameValidationError", "Contains illegal character."),
            E.CANNOT_BE_EMPTY: translate("NameValidationError", "Cannot be empty."),
            E.NOT_WINDOWS_FRIENDLY: translate("NameValidationError", "This name is discouraged for compatibility with Windows."),
            E.NAME_TAKEN: translate("NameValidationError", "This name is already taken."),
        }

    @staticmethod
    def _init_sidebarItems():
        from gitfourchette.sidebar.sidebarmodel import EItem as E
        return {
            E.UncommittedChanges: translate("SidebarModel", "Changes"),
            E.LocalBranchesHeader: translate("SidebarModel", "Local Branches"),
            E.StashesHeader: translate("SidebarModel", "Stashes"),
            E.RemotesHeader: translate("SidebarModel", "Remotes"),
            E.TagsHeader: translate("SidebarModel", "Tags"),
            E.SubmodulesHeader: translate("SidebarModel", "Submodules"),
            E.LocalBranch: translate("SidebarModel", "Local branch"),
            E.DetachedHead: translate("SidebarModel", "Detached HEAD"),
            E.UnbornHead: translate("SidebarModel", "Unborn HEAD"),
            E.RemoteBranch: translate("SidebarModel", "Remote branch"),
            E.Stash: translate("SidebarModel", "Stash"),
            E.Remote: translate("SidebarModel", "Remote"),
            E.Tag: translate("SidebarModel", "Tag"),
            E.Submodule: translate("SidebarModel", "Submodules"),
            E.Spacer: "---",
        }

    @staticmethod
    def _init_sidebarModes():
        from gitfourchette.sidebar.sidebarmodel import SidebarTabMode as E
        return {
            E.Branches: translate("SidebarModel", "Branches & Remotes"),
            E.Stashes: translate("SidebarModel", "Stashes"),
            E.Tags: translate("SidebarModel", "Tags"),
            E.Submodules: translate("SidebarModel", "Submodules"),
        }

    @staticmethod
    def _init_diffStatusChars():
        # see git_diff_status_char (diff_print.c)
        return {
            "A": translate("git", "added"),
            "C": translate("git", "copied"),
            "D": translate("git", "deleted"),
            "I": translate("git", "ignored"),
            "M": translate("git", "modified"),
            "R": translate("git", "renamed"),
            "T": translate("git", "file type changed"),
            "U": translate("git", "merge conflict"),  # "updated but unmerged"
            "X": translate("git", "unreadable"),
            "?": translate("git", "untracked"),
        }

    @staticmethod
    def _init_fileModes():
        return {
            0: translate("git", "deleted", "unreadable/deleted file mode 0o000000"),
            FileMode.BLOB: translate("git", "regular file", "default file mode 0o100644"),
            FileMode.BLOB_EXECUTABLE: translate("git", "executable file", "executable file mode 0o100755"),
            FileMode.LINK: translate("git", "symbolic link", "as in 'symlink' - file mode 0o120000"),
            FileMode.TREE: translate("git", "directory tree", "as in 'directory tree' - file mode 0o40000"),
            FileMode.COMMIT: translate("git", "commit", "'commit' file mode 0o160000"),
        }

    @staticmethod
    def _init_shortFileModes():
        # Intentionally untranslated.
        return {
            0: "",
            FileMode.BLOB: "",
            FileMode.BLOB_EXECUTABLE: "+x",
            FileMode.LINK: "link",
            FileMode.TREE: "tree",
            FileMode.COMMIT: "commit",
        }

    @staticmethod
    def _init_patchPurposes():
        from gitfourchette.toolbox.gitutils import PatchPurpose as pp
        return {
            pp.STAGE: translate("PatchPurpose", "Stage"),
            pp.UNSTAGE: translate("PatchPurpose", "Unstage"),
            pp.DISCARD: translate("PatchPurpose", "Discard"),
            pp.LINES | pp.STAGE: translate("PatchPurpose", "Stage lines"),
            pp.LINES | pp.UNSTAGE: translate("PatchPurpose", "Unstage lines"),
            pp.LINES | pp.DISCARD: translate("PatchPurpose", "Discard lines"),
            pp.HUNK | pp.STAGE: translate("PatchPurpose", "Stage hunk"),
            pp.HUNK | pp.UNSTAGE: translate("PatchPurpose", "Unstage hunk"),
            pp.HUNK | pp.DISCARD: translate("PatchPurpose", "Discard hunk"),
            pp.FILE | pp.STAGE: translate("PatchPurpose", "Stage file"),
            pp.FILE | pp.UNSTAGE: translate("PatchPurpose", "Unstage file"),
            pp.FILE | pp.DISCARD: translate("PatchPurpose", "Discard file"),
        }

    @staticmethod
    def _init_prefKeys():
        return {
            "general": translate("Prefs", "General"),
            "diff": translate("Prefs", "Diff"),
            "tabs": translate("Prefs", "Tabs"),
            "graph": translate("Prefs", "Commit History"),
            "trash": translate("Prefs", "Trash"),
            "external": translate("Prefs", "External Tools"),
            "debug": translate("Prefs", "Advanced"),

            "language": translate("Prefs", "Language"),
            "qtStyle": translate("Prefs", "Theme"),
            "shortHashChars": translate("Prefs", "Shorten hashes to # characters"),
            "shortTimeFormat": translate("Prefs", "Date/time format"),
            "pathDisplayStyle": translate("Prefs", "Path display style"),
            "authorDisplayStyle": translate("Prefs", "Author display style"),
            "maxRecentRepos": translate("Prefs", "Remember up to # recent repositories"),
            "showStatusBar": translate("Prefs", "Show status bar"),
            "showToolBar": translate("Prefs", "Show toolbar"),
            "showMenuBar": translate("Prefs", "Show menu bar (once hidden, press Alt to show it again)"),
            "resetDontShowAgain": translate("Prefs", "Restore all “don’t show this again” messages"),

            "diff_font": translate("Prefs", "Font"),
            "diff_tabSpaces": translate("Prefs", "One tab is # spaces"),
            "diff_contextLines": translate("Prefs", "Show up to # context lines"),
            "diff_largeFileThresholdKB": translate("Prefs", "Load diffs up to # KB"),
            "diff_imageFileThresholdKB": translate("Prefs", "Load images up to # KB"),
            "diff_wordWrap": translate("Prefs", "Word wrap"),
            "diff_showStrayCRs": translate("Prefs", "Display alien line endings (CRLF)"),
            "diff_colorblind": translate("Prefs", "Colorblind-friendly color scheme"),
            "diff_colorblind_help": "<html>" + translate(
                "Prefs",
                "Tick this if you have trouble distinguishing red and green. "
                "The diff will use a yellow and blue color scheme instead."),

            "tabs_closeButton": translate("Prefs", "Show tab close button"),
            "tabs_expanding": translate("Prefs", "Tab bar takes all available width"),
            "tabs_autoHide": translate("Prefs", "Auto-hide tab bar if there’s just 1 tab"),
            "tabs_doubleClickOpensFolder": translate("Prefs", "Double-click a tab to open repo folder"),

            "graph_chronologicalOrder": translate("Prefs", "Sort commits"),
            "graph_chronologicalOrder_true": translate("Prefs", "Chronologically"),
            "graph_chronologicalOrder_false": translate("Prefs", "Topologically"),
            "graph_chronologicalOrder_help": translate(
                "Prefs",
                "<p><b>Chronological mode</b> lets you stay on top of the latest activity in the repository. "
                "The most recent commits always show up at the top of the graph. "
                "However, the graph can get messy when multiple branches receive commits in the same timeframe.</p>"
                "<p><b>Topological mode</b> makes the graph easier to read. It attempts to present sequences of "
                "commits within a branch in a linear fashion. Since this is not a strictly chronological "
                "mode, you may have to do more scrolling to see the latest changes in various branches.</p>"),

            "graph_rowHeight": translate("Prefs", "Row spacing"),
            "graph_flattenLanes": translate("Prefs", "Squeeze branch lanes in graph"),
            "graph_authorDiffAsterisk": translate("Prefs", "Mark author/committer signature differences"),
            "graph_authorDiffAsterisk_help": "<html>" + translate(
                "Prefs",
                "<p>The commit history displays information about a commit’s <b>author</b> &ndash; "
                "their name and the date at which they made the commit. But in some cases, a commit "
                "might have been revised by someone else than the original author &ndash; "
                "this person is called the <b>committer</b>.</p>"
                "<p>If this option is ticked, an asterisk (*) will appear after the author’s name "
                "and/or date if they differ from the committer’s for any given commit.</p>"
                "<p>Note that you can always hover over the author’s name or date to obtain "
                "detailed information about the author and the committer.</p>"),

            "trash_maxFiles": translate("Prefs", "The trash keeps up to # discarded patches"),
            "trash_maxFileSizeKB": translate("Prefs", "Patches bigger than # KB won’t be salvaged"),
            "trash_HEADER": translate(
                "Prefs",
                "When you discard changes from the working directory, {app} keeps a temporary copy in a hidden "
                "“trash” folder. This gives you a last resort to rescue changes that you have discarded by mistake. "
                "You can look around this trash folder via <i>“Help &rarr; Open Trash”</i>."),

            "debug_verbosity": translate("Prefs", "Logging verbosity"),
            "debug_hideStashJunkParents": translate("Prefs", "Hide synthetic parents of stash commits"),
            "debug_autoRefresh": translate("Prefs", "Auto-refresh when app regains focus"),
            "debug_modalSidebar": translate("Prefs", "Modal sidebar"),
            "debug_smoothScroll": translate("Prefs", "Smooth scrolling (where applicable)"),
            "debug_forceQtApi": translate("Prefs", "Preferred Qt binding"),
            "debug_forceQtApi_help": translate(
                "Prefs", "<p>After restarting, {app} will use this Qt binding if available.</p><p>You can also pass "
                         "the name of a Qt binding via the “QT_API” environment variable.</p>"),

            "external_editor": translate("Prefs", "Text editor"),
            "external_diff": translate("Prefs", "Diff tool"),
            "external_diff_help": "<p style='white-space: pre'>" + translate(
                "Prefs", "Argument placeholders:"
                         "\n<code>$L</code> - Old/Left"
                         "\n<code>$R</code> - New/Right"
            ),
            "external_merge": translate("Prefs", "Merge tool"),
            "external_merge_help": "<p style='white-space: pre'>" + translate(
                "Prefs", "Argument placeholders:"
                         "\n<code>$B</code> - Ancestor / Base / Center"
                         "\n<code>$L</code> - Ours / Local / Left"
                         "\n<code>$R</code> - Theirs / Remote / Right"
                         "\n<code>$M</code> - Merged / Output / Result"
            ),

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

            "QTAPI_AUTOMATIC": translate("Prefs", "Automatic (recommended)", "automatic choice of qt binding"),
            "QTAPI_PYSIDE6": "PySide6",
            "QTAPI_PYQT6": "PyQt6",
            "QTAPI_PYQT5": "PyQt5",
        }

    @staticmethod
    def _init_conflictHelp():
        return {
            "DELETED_BY_US": translate(
                "ConflictView",
                "<b>Deleted by us:</b> this file was deleted from <i>our</i> branch, "
                "but <i>their</i> branch kept it and made changes to it."),

            "DELETED_BY_THEM": translate(
                "ConflictView",
                "<b>Deleted by them:</b> we’ve made changes to this file, "
                "but <i>their</i> branch has deleted it."),

            "DELETED_BY_BOTH": translate(
                "ConflictView",
                "<b>Deleted by both sides:</b> the file was deleted from <i>our</i> branch, "
                "and <i>their</i> branch has deleted it too."),

            "MODIFIED_BY_BOTH": translate(
                "ConflictView",
                "<b>Modified by both sides:</b> This file has received changes "
                "from both <i>our</i> branch and <i>their</i> branch."),

            "ADDED_BY_BOTH": translate(
                "ConflictView",
                "<b>Added by both sides:</b> This file has been created in "
                "both <i>our</i> branch and <i>their</i> branch, independently "
                "from each other. So, there is no common ancestor."),

            "ADDED_BY_THEM": translate("ConflictView", "<b>Added by them</b>, no common ancestor."),

            "ADDED_BY_US": translate("ConflictView", "<b>Added by us</b>, no common ancestor."),

            "tool": translate(
                "ConflictView",
                "You will be able to merge the changes in {tool}. When you are done merging, "
                "save the file in {tool} and come back to {app} to finish solving the conflict."),

            "ours": translate(
                "ConflictView",
                "Reject incoming changes. The file won’t be modified from its current state in HEAD."),

            "theirs": translate(
                "ConflictView",
                "Accept incoming changes. The file will be <b>replaced</b> with the incoming version."),

            "dbutheirs": translate(
                "ConflictView",
                "Accept incoming changes. The file will be added back to your branch with the incoming changes."),

            "dbuours": translate(
                "ConflictView",
                "Reject incoming changes. The file won’t be added back to your branch."),

            "dbtours": translate(
                "ConflictView",
                "Reject incoming deletion. Our version of the file will be kept intact."),

            "dbttheirs": translate(
                "ConflictView",
                "Accept incoming deletion. The file will be deleted."),

            "dbbnuke": translate(
                "ConflictView",
                "The file will be deleted."),
        }
