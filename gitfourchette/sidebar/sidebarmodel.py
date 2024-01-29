from contextlib import suppress
import logging
import enum
from typing import Any, Iterable

from gitfourchette import settings
from gitfourchette.appconsts import ACTIVE_BULLET
from gitfourchette.porcelain import *
from gitfourchette.qt import *
from gitfourchette.toolbox import *
from gitfourchette.trtables import TrTables
from gitfourchette.repostate import RepoState

logger = logging.getLogger(__name__)

ROLE_USERDATA = Qt.ItemDataRole.UserRole + 0
ROLE_EITEM = Qt.ItemDataRole.UserRole + 1
ROLE_ISHIDDEN = Qt.ItemDataRole.UserRole + 2
ROLE_REF = Qt.ItemDataRole.UserRole + 3

MODAL_SIDEBAR = not settings.TEST_MODE and settings.prefs.debug_modalSidebar  # do not change while app is running


class SidebarTabMode(enum.IntEnum):
    NonModal = -1
    Branches = 0
    Stashes = 1
    Tags = 2
    Submodules = 3


class EItem(enum.IntEnum):
    UncommittedChanges = enum.auto()
    LocalBranchesHeader = enum.auto()
    StashesHeader = enum.auto()
    RemotesHeader = enum.auto()
    TagsHeader = enum.auto()
    SubmodulesHeader = enum.auto()
    LocalBranch = enum.auto()
    DetachedHead = enum.auto()
    UnbornHead = enum.auto()
    Stash = enum.auto()
    Remote = enum.auto()
    RemoteBranch = enum.auto()
    Tag = enum.auto()
    Submodule = enum.auto()
    Spacer = enum.auto()


HEADER_ITEMS_NONMODAL = [
    EItem.UncommittedChanges,
    EItem.Spacer,
    EItem.LocalBranchesHeader,
    EItem.Spacer,
    EItem.RemotesHeader,
    EItem.Spacer,
    EItem.TagsHeader,
    EItem.Spacer,
    EItem.StashesHeader,
    EItem.Spacer,
    EItem.SubmodulesHeader,
]

HEADER_ITEMS_MODAL = [
    [
        EItem.LocalBranchesHeader,
        EItem.Spacer,
        EItem.RemotesHeader,
    ],
    [EItem.StashesHeader],
    [EItem.TagsHeader],
    [EItem.SubmodulesHeader]
]

ALWAYS_EXPAND = [] if not MODAL_SIDEBAR else [
    EItem.LocalBranchesHeader,
    EItem.RemotesHeader,
    EItem.TagsHeader,
    EItem.StashesHeader,
    EItem.SubmodulesHeader,
]

LEAF_ITEMS = [
    EItem.Spacer,
    EItem.LocalBranch,
    EItem.Stash,
    EItem.RemoteBranch,
    EItem.Tag,
    EItem.UnbornHead,
    EItem.DetachedHead,
    EItem.UncommittedChanges,
    EItem.Submodule,
]

UNINDENT_ITEMS = {
    EItem.LocalBranch: -1,
    EItem.UnbornHead: -1,
    EItem.DetachedHead: -1,
    EItem.Stash: -1,
    EItem.Tag: -1,
    EItem.Submodule: -1,
    EItem.Remote: -1,
    EItem.RemoteBranch: -1,
}

if MODAL_SIDEBAR: UNINDENT_ITEMS.update({
    EItem.LocalBranchesHeader: -1,
    EItem.RemotesHeader: -1,
    EItem.StashesHeader: -1,
    EItem.TagsHeader: -1,
    EItem.SubmodulesHeader: -1,
})


class SidebarModel(QAbstractItemModel):
    repoState: RepoState | None
    repo: Repo | None
    _localBranches: list[str]
    _unbornHead: str
    _detachedHead: str
    _checkedOut: str; "Shorthand of checked-out local branch"
    _checkedOutUpstream: str; "Shorthand of the checked-out branch's upstream"
    _stashes: list[Stash]
    _remotes: list[str]
    _remoteURLs: list[str]
    _remoteBranchesDict: dict[str, list[str]]
    _tags: list[str]
    _submodules: list[str]
    _hiddenBranches: list[str]
    _hiddenStashCommits: list[str]
    _hideAllStashes: bool
    _hiddenRemotes: list[str]

    _cachedTooltipIndex: QModelIndex | None
    _cachedTooltipText: str

    modeId: int

    @staticmethod
    def packId(eid: EItem, offset: int = 0) -> int:
        """ Pack an EItem and an offset (row) into an internal ID to be associated with a QModelIndex. """
        return eid.value | (offset << 8)

    @staticmethod
    def unpackItem(index: QModelIndex) -> EItem:
        """ Extract an EItem from the index's internal ID. """
        return EItem(index.internalId() & 0xFF)

    @staticmethod
    def unpackOffset(index: QModelIndex) -> int:
        """ Extract an offset (row) from the index's internal ID. """
        return index.internalId() >> 8

    @staticmethod
    def unpackItemAndData(index: QModelIndex) -> tuple[EItem, str]:
        item = SidebarModel.unpackItem(index)
        data = index.data(Qt.ItemDataRole.UserRole) or ""
        assert type(data) is str
        return item, data

    @staticmethod
    def getCollapseHash(index: QModelIndex):
        item, data = SidebarModel.unpackItemAndData(index)
        return f"{item}-{data}"
        # Warning: it's tempting to replace this with something like "hash(data) << 8 | item",
        # but hash(data) doesn't return stable values across different Python sessions,
        # so it's not suitable for persistent storage (in history.json).

    @property
    def _parentWidget(self) -> QWidget:
        return QObject.parent(self)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.modeId = -1
        self.clear()

    @property
    def rootLayoutDef(self):
        if self.modeId == SidebarTabMode.NonModal:
            return HEADER_ITEMS_NONMODAL
        else:
            return HEADER_ITEMS_MODAL[self.modeId]

    def clear(self, emitSignals=True):
        if emitSignals:
            self.beginResetModel()

        self.repo = None
        self._localBranches = []
        self._unbornHead = ""
        self._detachedHead = ""
        self._checkedOut = ""
        self._checkedOutUpstream = ""
        self._stashes = []
        self._remotes = []
        self._remoteURLs = []
        self._remoteBranchesDict = {}
        self._tags = []
        self._submodules = []
        self._hiddenBranches = []
        self._hiddenStashCommits = []
        self._hideAllStashes = False
        self._hiddenRemotes = []

        self._cachedTooltipIndex = None
        self._cachedTooltipText = ""

        if emitSignals:
            self.endResetModel()

    def switchMode(self, i: int):
        self.beginResetModel()
        self.modeId = i
        self.endResetModel()

    @benchmark
    def refreshCache(self, repoState: RepoState):
        self.beginResetModel()

        repo = repoState.repo
        refCache = repoState.refCache

        self.clear(emitSignals=False)
        self.repo = repo
        self.repoState = repoState

        # Remote list
        with Benchmark("Sidebar/Remotes"):
            for r in repo.remotes:
                self._remotes.append(r.name)
                self._remoteURLs.append(r.url)
                self._remoteBranchesDict[r.name] = []

        # Refs
        with Benchmark("Sidebar/Refs"):
            for name in reversed(refCache):  # reversed because refCache sorts tips by ASCENDING commit time
                prefix, shorthand = RefPrefix.split(name)
                if prefix == RefPrefix.HEADS:
                    self._localBranches.append(shorthand)
                    # upstream = repo.branches.local[name].upstream  # a bit costly
                    # if not upstream:
                    #     self._tracking.append("")
                    # else:
                    #     self._tracking.append(upstream.shorthand)
                elif prefix == RefPrefix.REMOTES:
                    remote, branchName = split_remote_branch_shorthand(shorthand)
                    try:
                        self._remoteBranchesDict[remote].append(branchName)
                    except KeyError:
                        logger.warning(f"Refresh cache: missing remote: {remote}")
                elif prefix == RefPrefix.TAGS:
                    self._tags.append(shorthand)
                elif name == "HEAD" or name.startswith("stash@{"):
                    pass  # handled separately
                else:
                    logger.warning(f"Refresh cache: unsupported ref prefix: {name}")

            # Sort remote branches
            for remote in self._remoteBranchesDict:
                self._remoteBranchesDict[remote] = sorted(self._remoteBranchesDict[remote])

        # HEAD
        with Benchmark("Sidebar/HEAD"):
            self._unbornHead = ""
            self._detachedHead = ""
            self._checkedOut = ""
            self._checkedOutUpstream = ""

            try:
                # Try to get the name of the checked-out branch
                checkedOut = repo.head.name

            except GitError:
                # Unborn HEAD - Get name of unborn branch
                assert repo.head_is_unborn
                target: str = repo.lookup_reference("HEAD").target
                target = target.removeprefix(RefPrefix.HEADS)
                self._unbornHead = target

            else:
                # It's not unborn
                if checkedOut == 'HEAD':
                    # Detached head, leave self._checkedOut blank
                    assert repo.head_is_detached
                    self._detachedHead = repo.head.target.hex
                else:
                    # We're on a branch
                    assert checkedOut.startswith(RefPrefix.HEADS)
                    checkedOut = checkedOut.removeprefix(RefPrefix.HEADS)
                    self._checkedOut = checkedOut

                    # Try to get the upstream (.upstream_name raises KeyError if there isn't one)
                    with suppress(KeyError):
                        branch = repo.branches.local[checkedOut]
                        upstream = branch.upstream_name  # This can be a bit expensive
                        upstream = upstream.removeprefix(RefPrefix.REMOTES)  # Convert to shorthand
                        self._checkedOutUpstream = upstream

        # Stashes
        with Benchmark("Sidebar/Stashes"):
            self._stashes = repo.listall_stashes()

        # Submodules
        with Benchmark("Sidebar/Submodules"):
            self._submodules = repo.listall_submodules_fast()

        self._hiddenBranches = repoState.uiPrefs.hiddenBranches
        self._hiddenStashCommits = repoState.uiPrefs.hiddenStashCommits
        self._hideAllStashes = repoState.uiPrefs.hideAllStashes
        self._hiddenRemotes = repoState.uiPrefs.hiddenRemotes

        with Benchmark("Sidebar/endResetModel"):
            self.endResetModel()

    def columnCount(self, parent: QModelIndex) -> int:
        return 1

    def index(self, row, column, parent: QModelIndex = None) -> QModelIndex:
        if not self.repo or column != 0 or row < 0:
            return QModelIndex()

        if not parent or not parent.isValid():  # root
            return self.createIndex(row, 0, self.rootLayoutDef[row].value)

        item = self.unpackItem(parent)

        if item == EItem.LocalBranchesHeader:
            y = 0

            if self._unbornHead:
                if y == row:
                    return self.createIndex(row, 0, self.packId(EItem.UnbornHead))
                y += 1

            if self._detachedHead:
                if y == row:
                    return self.createIndex(row, 0, self.packId(EItem.DetachedHead))
                y += 1

            return self.createIndex(row, 0, self.packId(EItem.LocalBranch, row - y))

        elif item == EItem.RemotesHeader:
            return self.createIndex(row, 0, self.packId(EItem.Remote))

        elif item == EItem.Remote:
            return self.createIndex(row, 0, self.packId(EItem.RemoteBranch, parent.row()))

        elif item == EItem.TagsHeader:
            return self.createIndex(row, 0, self.packId(EItem.Tag))

        elif item == EItem.StashesHeader:
            return self.createIndex(row, 0, self.packId(EItem.Stash))

        elif item == EItem.SubmodulesHeader:
            return self.createIndex(row, 0, self.packId(EItem.Submodule))

        return QModelIndex()

    def parent(self, index: QModelIndex = QModelIndex()) -> QModelIndex:
        if not self.repo or not index.isValid():
            return QModelIndex()

        item = self.unpackItem(index)

        def makeParentIndex(parentHeader: EItem):
            return self.createIndex(self.rootLayoutDef.index(parentHeader), 0, self.packId(parentHeader))

        if item in self.rootLayoutDef:
            # it's a root node -- return invalid index because no parent
            return QModelIndex()

        elif item in [EItem.LocalBranch, EItem.DetachedHead, EItem.UnbornHead]:
            return makeParentIndex(EItem.LocalBranchesHeader)

        elif item == EItem.Remote:
            return makeParentIndex(EItem.RemotesHeader)

        elif item == EItem.RemoteBranch:
            remoteNo = self.unpackOffset(index)
            return self.createIndex(remoteNo, 0, self.packId(EItem.Remote))

        elif item == EItem.Tag:
            return makeParentIndex(EItem.TagsHeader)

        elif item == EItem.Stash:
            return makeParentIndex(EItem.StashesHeader)

        elif item == EItem.Submodule:
            return makeParentIndex(EItem.SubmodulesHeader)

        else:
            return QModelIndex()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if not self.repo:
            return 0

        if not parent.isValid():  # root
            return len(self.rootLayoutDef)

        item = self.unpackItem(parent)

        if item == EItem.LocalBranchesHeader:
            n = len(self._localBranches)
            if self._unbornHead:
                n += 1
            if self._detachedHead:
                n += 1
            return n

        elif item == EItem.RemotesHeader:
            return len(self._remotes)

        elif item == EItem.Remote:
            remoteName = self._remotes[parent.row()]
            return len(self._remoteBranchesDict[remoteName])

        elif item == EItem.TagsHeader:
            return len(self._tags)

        elif item == EItem.StashesHeader:
            return len(self._stashes)

        elif item == EItem.SubmodulesHeader:
            return len(self._submodules)

        else:
            return 0

    def hiddenBranchFont(self) -> QFont:
        font = self._parentWidget.font()
        font.setStrikeOut(True)
        return font

    def cacheTooltip(self, index: QModelIndex, text: str):
        self._cachedTooltipIndex = index
        self._cachedTooltipText = text

    def data(self, index: QModelIndex, role: Qt.ItemDataRole = Qt.ItemDataRole.DisplayRole) -> Any:
        if not self.repo:
            return None

        # Tooltips may show information that is expensive to obtain.
        # Try to reuse any tooltip that we may have cached for the same index.
        if role == Qt.ItemDataRole.ToolTipRole and index == self._cachedTooltipIndex:
            return self._cachedTooltipText

        row = index.row()
        item = self.unpackItem(index)

        if role == ROLE_EITEM:  # for testing (match by EItem type)
            return item.value

        displayRole = role == Qt.ItemDataRole.DisplayRole
        toolTipRole = role == Qt.ItemDataRole.ToolTipRole
        sizeHintRole = role == Qt.ItemDataRole.SizeHintRole
        fontRole = role == Qt.ItemDataRole.FontRole
        decorationRole = role == Qt.ItemDataRole.DecorationRole
        userRole = role == ROLE_USERDATA
        hiddenRole = role == ROLE_ISHIDDEN
        refRole = role == ROLE_REF

        if item == EItem.Spacer:
            if sizeHintRole:
                parentWidget: QWidget = QObject.parent(self)
                return QSize(-1, int(0.5 * parentWidget.fontMetrics().height()))
            else:
                return None

        elif item == EItem.LocalBranch:
            branchNo = self.unpackOffset(index)
            branchName = self._localBranches[branchNo]
            if displayRole:
                return branchName
            elif userRole:
                return branchName
            elif refRole:
                return F"refs/heads/{branchName}"
            elif toolTipRole:
                text = "<p style='white-space: pre'>"
                if branchName == self._checkedOut:
                    text += ACTIVE_BULLET + self.tr("This is the checked-out branch.") + "\n"
                text += self.tr("Local branch {0}").format(bquo(branchName))
                if self._checkedOutUpstream:
                    text += "\n" + self.tr("Upstream branch is {0}").format(hquo(self._checkedOutUpstream))
                self.cacheTooltip(index, text)
                return text
            elif hiddenRole:
                return F"refs/heads/{branchName}" in self._hiddenBranches
            elif fontRole:
                if F"refs/heads/{branchName}" in self._hiddenBranches:
                    return self.hiddenBranchFont()
                elif branchName == self._checkedOut:
                    font = self._parentWidget.font()
                    font.setWeight(QFont.Weight.Black)
                    return font
                else:
                    return None
            elif decorationRole:
                return stockIcon("git-branch" if branchName != self._checkedOut else "git-home")

        elif item == EItem.UnbornHead:
            if displayRole:
                return self.tr("[unborn]") + F" {self._unbornHead}"
            elif userRole:
                return self._unbornHead
            elif toolTipRole:
                text = "<p style='white-space: pre'>"
                text += self.tr("Local branch {0}")
                text += "<br>" + self.tr("Unborn HEAD: does not point to a commit yet.")
                text += "<br>" + self.tr("The branch will be created when you create the initial commit.")
                text = text.format(bquo(self._unbornHead))
                self.cacheTooltip(index, text)
                return text
            elif hiddenRole:
                return False

        elif item == EItem.DetachedHead:
            if displayRole:
                return self.tr("Detached HEAD")
            elif userRole:
                return self._detachedHead
            elif toolTipRole:
                caption = self.tr("Detached HEAD")
                return f"<p style='white-space: pre'>{caption} @ {self._detachedHead[:settings.prefs.shortHashChars]}"
            elif hiddenRole:
                return False
            elif refRole:
                return "HEAD"
            elif role == decorationRole:
                if MACOS or WINDOWS:
                    return stockIcon(QStyle.StandardPixmap.SP_MessageBoxWarning)
                else:
                    return stockIcon("achtung")

        elif item == EItem.Remote:
            if displayRole or userRole:
                return self._remotes[row]
            elif toolTipRole:
                return "<p style='white-space: pre'>" + escape(self._remoteURLs[row])
            elif fontRole:
                if self._remotes[row] in self._hiddenRemotes:
                    return self.hiddenBranchFont()
            elif hiddenRole:
                return False
            elif decorationRole:
                return stockIcon("git-remote")

        elif item == EItem.RemoteBranch:
            remoteNo = self.unpackOffset(index)
            remoteName = self._remotes[remoteNo]
            branchName = self._remoteBranchesDict[remoteName][row]
            if displayRole:
                return branchName
            elif refRole:
                return F"refs/remotes/{remoteName}/{branchName}"
            elif userRole:
                return F"{remoteName}/{branchName}"
            elif toolTipRole:
                text = ("<p style='white-space: pre'>" + self.tr("Remote-tracking branch {0}")
                        ).format(bquo(f"{remoteName}/{branchName}"))
                if self._checkedOutUpstream == f"{remoteName}/{branchName}":
                    text += "<br><i>" + self.tr("This is the upstream for the checked-out branch ({0}).").format(hquoe(self._checkedOut))
                return text
            elif fontRole:
                if F"refs/remotes/{remoteName}/{branchName}" in self._hiddenBranches:
                    return self.hiddenBranchFont()
                elif self._checkedOutUpstream == f"{remoteName}/{branchName}":
                    font = QFont(self._parentWidget.font())
                    font.setItalic(True)
                    font.setWeight(QFont.Weight.Medium)
                    return font
                else:
                    return None
            elif hiddenRole:
                return F"refs/remotes/{remoteName}/{branchName}" in self._hiddenBranches
            elif decorationRole:
                return stockIcon("git-branch")

        elif item == EItem.Tag:
            if displayRole or userRole:
                return self._tags[row]
            elif refRole:
                return F"refs/tags/{self._tags[row]}"
            elif hiddenRole:
                return False
            elif decorationRole:
                return stockIcon("git-tag")

        elif item == EItem.Stash:
            stash = self._stashes[row]
            if displayRole:
                return strip_stash_message(stash.message)
            elif refRole:
                return F"stash@{{{row}}}"
            elif toolTipRole:
                commit = self.repo.peel_commit(stash.commit_id)
                commitQdt = QDateTime.fromSecsSinceEpoch(commit.commit_time, Qt.TimeSpec.OffsetFromUTC, commit.commit_time_offset * 60)
                commitTimeStr = QLocale().toString(commitQdt, settings.prefs.shortTimeFormat)
                text = "<p style='white-space: pre'>"
                text += f"<b>stash@{{{row}}}</b>: {escape(stash.message)}<br/>"
                text += f"<b>{self.tr('date:')}</b> {commitTimeStr}"
                self.cacheTooltip(index, text)
                return text
            elif userRole:
                return stash.commit_id.hex
            elif fontRole:
                if stash.commit_id.hex in self._hiddenStashCommits:
                    return self.hiddenBranchFont()
                else:
                    return None
            elif hiddenRole:
                return stash.commit_id.hex in self._hiddenStashCommits
            elif decorationRole:
                return stockIcon("git-stash")

        elif item == EItem.Submodule:
            if displayRole:
                return self._submodules[row].rsplit("/", 1)[-1]
            elif toolTipRole:
                return self._submodules[row]
            elif userRole:
                return self._submodules[row]
            elif hiddenRole:
                return False
            elif decorationRole:
                return stockIcon("git-submodule")

        elif item == EItem.UncommittedChanges:
            if displayRole:
                changesText = self.tr("Uncommitted")
                numUncommittedChanges = self.repoState.numUncommittedChanges
                if numUncommittedChanges != 0:
                    changesText = f"({numUncommittedChanges}) " + changesText
                return changesText
            elif refRole:
                # Return fake ref so we can select Uncommitted Changes from elsewhere
                return "UNCOMMITTED_CHANGES"
            elif fontRole:
                font = self._parentWidget.font()
                font.setWeight(QFont.Weight.DemiBold)
                return font
            elif hiddenRole:
                return False
            elif decorationRole:
                return stockIcon("git-workdir")
            elif toolTipRole:
                return appendShortcutToToolTipText(self.tr("Go to Uncommitted Changes"), QKeySequence("Ctrl+U"))

        else:
            if displayRole:
                return TrTables.sidebarItem(item)
            elif refRole:
                return ""
            elif fontRole:
                font = self._parentWidget.font()
                font.setWeight(QFont.Weight.DemiBold)
                if item == EItem.StashesHeader and self._hideAllStashes:
                    font.setStrikeOut(True)
                return font
            elif hiddenRole:
                return False

        # fallback
        if sizeHintRole:
            return QSize(-1, int(1.15 * self._parentWidget.fontMetrics().height()))
        elif hiddenRole:
            return False

        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        item = self.unpackItem(index)

        if item == EItem.Spacer:
            return Qt.ItemFlag.NoItemFlags

        if item in ALWAYS_EXPAND:
            return Qt.ItemFlag.NoItemFlags

        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
