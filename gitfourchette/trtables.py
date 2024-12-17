# -----------------------------------------------------------------------------
# Copyright (C) 2024 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

from __future__ import annotations
from typing import TYPE_CHECKING

from gitfourchette.porcelain import *
from gitfourchette.qt import translate

if TYPE_CHECKING:
    from gitfourchette.toolbox import PatchPurpose
    from gitfourchette.sidebar.sidebarmodel import SidebarItem


class TrTables:
    _exceptionNames             : dict[str, str] = {}
    _nameValidationCodes        : dict[int, str] = {}
    _sidebarItems               : dict[SidebarItem, str] = {}
    _prefKeys                   : dict[str, str] = {}
    _diffStatusChars            : dict[str, str] = {}
    _fileModes                  : dict[FileMode, str] = {}
    _shortFileModes             : dict[FileMode, str] = {}
    _repositoryStates           : dict[RepositoryState, str] = {}
    _patchPurposes              : dict[PatchPurpose, str] = {}
    _patchPurposesPastTense     : dict[PatchPurpose, str] = {}
    _conflictSides              : dict[ConflictSides, str] = {}

    @classmethod
    def init(cls):
        if not cls._exceptionNames:
            cls.retranslate()

    @classmethod
    def retranslate(cls):
        cls._exceptionNames = cls._init_exceptionNames()
        cls._nameValidationCodes = cls._init_nameValidationCodes()
        cls._sidebarItems = cls._init_sidebarItems()
        cls._prefKeys = cls._init_prefKeys()
        cls._diffStatusChars = cls._init_diffStatusChars()
        cls._fileModes = cls._init_fileModes()
        cls._shortFileModes = cls._init_shortFileModes()
        cls._repositoryStates = cls._init_repositoryStates()
        cls._patchPurposes = cls._init_patchPurposes()
        cls._patchPurposesPastTense = cls._init_patchPurposesPastTense()
        cls._conflictSides = cls._init_conflictSides()

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
    def sidebarItem(cls, item: SidebarItem):
        try:
            return cls._sidebarItems[item]
        except KeyError:
            return "?"+str(item)

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
    def repositoryState(cls, s: RepositoryState):
        try:
            return cls._repositoryStates[s]
        except KeyError:
            return f"#{s}"

    @classmethod
    def patchPurpose(cls, purpose: PatchPurpose):
        return cls._patchPurposes.get(purpose, "???")

    @classmethod
    def patchPurposePastTense(cls, purpose: PatchPurpose):
        return cls._patchPurposesPastTense.get(purpose, "???")

    @classmethod
    def conflictSides(cls, key: ConflictSides):
        return cls._conflictSides.get(key, f"?{key}")

    @staticmethod
    def _init_exceptionNames():
        return {
            "ConnectionRefusedError": translate("Exception", "Connection refused"),
            "FileNotFoundError": translate("Exception", "File not found"),
            "PermissionError": translate("Exception", "Permission denied"),
            "GitError": translate("Exception", "Git error"),
            "NotImplementedError": translate("Exception", "Unsupported feature"),
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
            E.NAME_TAKEN_BY_REF: translate("NameValidationError", "This name is already taken."),
            E.NAME_TAKEN_BY_FOLDER: translate("NameValidationError", "This name is already taken by a folder."),
        }

    @staticmethod
    def _init_sidebarItems():
        from gitfourchette.sidebar.sidebarmodel import SidebarItem as E
        from gitfourchette.toolbox import toLengthVariants
        return {
            E.UncommittedChanges: toLengthVariants(translate("SidebarModel", "Uncommitted Changes|Changes")),
            E.LocalBranchesHeader: toLengthVariants(translate("SidebarModel", "Local Branches|Branches")),
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
            FileMode.TREE: translate("git", "subtree", "as in 'directory tree' - file mode 0o40000"),
            FileMode.COMMIT: translate("git", "subtree commit", "'commit' file mode 0o160000"),
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
            FileMode.COMMIT: "tree",
        }

    @staticmethod
    def _init_repositoryStates():
        return {
            RepositoryState.NONE                : translate("RepositoryState", "None"),
            RepositoryState.MERGE               : translate("RepositoryState", "Merging"),
            RepositoryState.REVERT              : translate("RepositoryState", "Reverting"),
            RepositoryState.REVERT_SEQUENCE     : translate("RepositoryState", "Reverting (sequence)"),
            RepositoryState.CHERRYPICK          : translate("RepositoryState", "Cherry-picking"),
            RepositoryState.CHERRYPICK_SEQUENCE : translate("RepositoryState", "Cherry-picking (sequence)"),
            RepositoryState.BISECT              : translate("RepositoryState", "Bisecting"),
            RepositoryState.REBASE              : translate("RepositoryState", "Rebasing"),
            RepositoryState.REBASE_INTERACTIVE  : translate("RepositoryState", "Rebasing (interactive)"),
            RepositoryState.REBASE_MERGE        : translate("RepositoryState", "Rebasing (merging)"),
            RepositoryState.APPLY_MAILBOX       : "Apply Mailbox",  # intentionally untranslated
            RepositoryState.APPLY_MAILBOX_OR_REBASE: "Apply Mailbox or Rebase",  # intentionally untranslated
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
    def _init_patchPurposesPastTense():
        from gitfourchette.toolbox.gitutils import PatchPurpose as pp
        return {
            pp.STAGE: translate("PatchPurpose", "Staged."),
            pp.UNSTAGE: translate("PatchPurpose", "Unstaged."),
            pp.DISCARD: translate("PatchPurpose", "Discarded."),
            pp.LINES | pp.STAGE: translate("PatchPurpose", "Lines staged."),
            pp.LINES | pp.UNSTAGE: translate("PatchPurpose", "Lines unstaged."),
            pp.LINES | pp.DISCARD: translate("PatchPurpose", "Lines discarded."),
            pp.HUNK | pp.STAGE: translate("PatchPurpose", "Hunk staged."),
            pp.HUNK | pp.UNSTAGE: translate("PatchPurpose", "Hunk unstaged."),
            pp.HUNK | pp.DISCARD: translate("PatchPurpose", "Hunk discarded."),
            pp.FILE | pp.STAGE: translate("PatchPurpose", "File staged."),
            pp.FILE | pp.UNSTAGE: translate("PatchPurpose", "File unstaged."),
            pp.FILE | pp.DISCARD: translate("PatchPurpose", "File discarded."),
        }

    @staticmethod
    def _init_prefKeys():
        return {
            "general": translate("Prefs", "General"),
            "diff": translate("Prefs", "Code Diff"),
            "imageDiff": translate("Prefs", "Image Diff"),
            "tabs": translate("Prefs", "Tabs"),
            "graph": translate("Prefs", "Commit History"),
            "trash": translate("Prefs", "Trash"),
            "external": translate("Prefs", "External Tools"),
            "advanced": translate("Prefs", "Advanced"),

            "language": translate("Prefs", "Language"),
            "qtStyle": translate("Prefs", "Theme"),
            "shortHashChars": translate("Prefs", "Shorten hashes to # characters"),
            "shortTimeFormat": translate("Prefs", "Date/time format"),
            "pathDisplayStyle": translate("Prefs", "Path display style"),
            "authorDisplayStyle": translate("Prefs", "Author display style"),
            "maxRecentRepos": translate("Prefs", "Remember up to # recent repositories"),
            "showStatusBar": translate("Prefs", "Show status bar"),
            "showToolBar": translate("Prefs", "Show toolbar"),
            "showMenuBar": translate("Prefs", "Show menu bar"),
            "showMenuBar_help": translate("Prefs", "When the menu bar is hidden, press the Alt key to show it again."),
            "resetDontShowAgain": translate("Prefs", "Restore all “don’t show this again” messages"),
            "middleClickToStage": translate("Prefs", "Middle-click a file name to stage/unstage the file"),

            "font": translate("Prefs", "Font"),
            "tabSpaces": translate("Prefs", "One tab is # spaces"),
            "contextLines": translate("Prefs", "Show up to # context lines"),
            "contextLines_help": translate("Prefs", "Amount of unmodified lines to show around red or green lines in a diff."),
            "largeFileThresholdKB": translate("Prefs", "Load diffs up to # KB"),
            "imageFileThresholdKB": translate("Prefs", "Load images up to # KB"),
            "wordWrap": translate("Prefs", "Word wrap"),
            "showStrayCRs": translate("Prefs", "Display alien line endings (CRLF)"),
            "colorblind": translate("Prefs", "Colorblind-friendly color scheme"),
            "colorblind_help": "<html>" + translate(
                "Prefs",
                "Tick this if you have trouble distinguishing red and green. "
                "The diff will use a yellow and blue color scheme instead."),
            "renderSvg": translate("Prefs", "Treat SVG files as"),

            "tabCloseButton": translate("Prefs", "Show tab close button"),
            "expandingTabs": translate("Prefs", "Expand tabs to available width"),
            "autoHideTabs": translate("Prefs", "Auto-hide tabs if only one repo is open"),
            "doubleClickTabOpensFolder": translate("Prefs", "Double-click a tab to open repo folder"),

            "chronologicalOrder": translate("Prefs", "Sort commits"),
            "chronologicalOrder_true": translate("Prefs", "Chronologically"),
            "chronologicalOrder_false": translate("Prefs", "Topologically"),
            "chronologicalOrder_help": translate(
                "Prefs",
                "<p><b>Chronological mode</b> lets you stay on top of the latest activity in the repository. "
                "The most recent commits always show up at the top of the graph. "
                "However, the graph can get messy when multiple branches receive commits in the same timeframe.</p>"
                "<p><b>Topological mode</b> makes the graph easier to read. It attempts to present sequences of "
                "commits within a branch in a linear fashion. Since this is not a strictly chronological "
                "mode, you may have to do more scrolling to see the latest changes in various branches.</p>"),

            "graphRowHeight": translate("Prefs", "Row spacing"),
            "flattenLanes": translate("Prefs", "Squeeze branch lanes in graph"),
            "authorDiffAsterisk": translate("Prefs", "Mark author/committer signature differences"),
            "authorDiffAsterisk_help": "<html>" + translate(
                "Prefs",
                "<p>The commit history displays information about a commit’s <b>author</b> &ndash; "
                "their name and the date at which they made the commit. But in some cases, a commit "
                "might have been revised by someone else than the original author &ndash; "
                "this person is called the <b>committer</b>.</p>"
                "<p>If this option is ticked, an asterisk (*) will appear after the author’s name "
                "and/or date if they differ from the committer’s for any given commit.</p>"
                "<p>Note that you can always hover over the author’s name or date to obtain "
                "detailed information about the author and the committer.</p>"),
            "maxCommits": translate("Prefs", "Load up to # commits in the history"),
            "maxCommits_help": translate("Prefs", "Set to 0 to always load the full commit history."),
            "alternatingRowColors": translate("Prefs", "Draw rows using alternating background colors"),

            "maxTrashFiles": translate("Prefs", "The trash keeps up to # discarded patches"),
            "maxTrashFileKB": translate("Prefs", "Patches bigger than # KB won’t be salvaged"),
            "trash_HEADER": translate(
                "Prefs",
                "When you discard changes from the working directory, {app} keeps a temporary copy in a hidden "
                "“trash” folder. This gives you a last resort to rescue changes that you have discarded by mistake. "
                "You can look around this trash folder via <i>“Help &rarr; Open Trash”</i>."),

            "verbosity": translate("Prefs", "Logging verbosity"),
            "autoRefresh": translate("Prefs", "Auto-refresh when app regains focus"),
            "animations": translate("Prefs", "Animation effects"),
            "smoothScroll": translate("Prefs", "Smooth scrolling (where applicable)"),
            "forceQtApi": translate("Prefs", "Preferred Qt binding"),
            "forceQtApi_help": translate(
                "Prefs", "<p>After restarting, {app} will use this Qt binding if available.</p><p>You can also pass "
                         "the name of a Qt binding via the “QT_API” environment variable.</p>"),

            "externalEditor": translate("Prefs", "Text editor"),
            "externalDiff": translate("Prefs", "Diff tool"),
            "externalDiff_help": "<p style='white-space: pre'>" + translate(
                "Prefs", "Argument placeholders:"
                         "\n<code>$L</code> - Old/Left"
                         "\n<code>$R</code> - New/Right"
            ),
            "externalMerge": translate("Prefs", "Merge tool"),
            "externalMerge_help": "<p style='white-space: pre'>" + translate(
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
    def _init_conflictSides():
        return {
            ConflictSides.MODIFIED_BY_BOTH: translate("ConflictSides", "modified by both sides"),
            ConflictSides.DELETED_BY_US: translate("ConflictSides", "deleted by us"),
            ConflictSides.DELETED_BY_THEM: translate("ConflictSides", "deleted by them"),
            ConflictSides.DELETED_BY_BOTH: translate("ConflictSides", "deleted by both sides"),
            ConflictSides.ADDED_BY_US: translate("ConflictSides", "added by us"),
            ConflictSides.ADDED_BY_THEM: translate("ConflictSides", "added by them"),
            ConflictSides.ADDED_BY_BOTH: translate("ConflictSides", "added by both sides"),
        }
