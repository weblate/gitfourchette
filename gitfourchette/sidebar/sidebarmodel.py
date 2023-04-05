from gitfourchette import porcelain
from gitfourchette.globalshortcuts import GlobalShortcuts
from gitfourchette.qt import *
from gitfourchette.toolbox import *
from gitfourchette.repostate import RepoState
from typing import Any, Iterable
import contextlib
import enum
import pygit2

ROLE_USERDATA = Qt.ItemDataRole.UserRole + 0
ROLE_EITEM = Qt.ItemDataRole.UserRole + 1
ROLE_ISHIDDEN = Qt.ItemDataRole.UserRole + 2
ROLE_REF = Qt.ItemDataRole.UserRole + 3

ACTIVE_BULLET = "★ "


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


HEADER_ITEMS = [
    EItem.UncommittedChanges,
    EItem.Spacer,
    EItem.StashesHeader,
    EItem.Spacer,
    EItem.LocalBranchesHeader,
    EItem.Spacer,
    EItem.RemotesHeader,
    EItem.Spacer,
    EItem.TagsHeader,
    EItem.Spacer,
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

UNINDENT_ITEMS = [
    EItem.LocalBranch,
    EItem.UnbornHead,
    EItem.DetachedHead,
    EItem.Stash,
    EItem.Tag,
    EItem.Submodule,
]


class SidebarModel(QAbstractItemModel):
    repo: pygit2.Repository | None
    _localBranches: list[str]
    _tracking: list[str]
    _unbornHead: str
    _detachedHead: str
    _checkedOut: str
    _stashes: list[pygit2.Stash]
    _remotes: list[str]
    _remoteURLs: list[str]
    _remoteBranchesDict: dict[str, list[str]]
    _tags: list[str]
    _submodules: list[str]
    _hiddenBranches: list[str]

    @staticmethod
    def packId(eid: EItem, offset: int = 0) -> int:
        return eid.value | (offset << 8)

    @staticmethod
    def unpackItem(index: QModelIndex) -> EItem:
        return EItem(index.internalId() & 0xFF)

    @staticmethod
    def unpackOffset(index: QModelIndex) -> int:
        return index.internalId() >> 8

    @staticmethod
    def unpackItemAndData(index: QModelIndex):
        return SidebarModel.unpackItem(index), index.data(Qt.ItemDataRole.UserRole)

    @property
    def _parentWidget(self) -> QWidget:
        return QObject.parent(self)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.clear()

    def clear(self, emitSignals=True):
        if emitSignals:
            self.beginResetModel()

        self.repo = None
        self._localBranches = []
        self._tracking = []
        self._unbornHead = ""
        self._detachedHead = ""
        self._checkedOut = ""
        self._stashes = []
        self._remotes = []
        self._remoteURLs = []
        self._remoteBranchesDict = {}
        self._tags = []
        self._submodules = []
        self._hiddenBranches = []

        if emitSignals:
            self.endResetModel()

    def refreshCache(self, repo: pygit2.Repository, hiddenBranches: list[str], refCache: Iterable[str]):
        self.beginResetModel()

        self.clear(emitSignals=False)
        self.repo = repo

        # Remote list
        with Benchmark("Sidebar/Remotes"):
            for r in repo.remotes:
                self._remotes.append(r.name)
                self._remoteURLs.append(r.url)
                self._remoteBranchesDict[r.name] = []

        # Refs
        with Benchmark("Sidebar/Refs"):
            for name in refCache:
                if name.startswith(porcelain.HEADS_PREFIX):
                    name = name.removeprefix(porcelain.HEADS_PREFIX)
                    self._localBranches.append(name)
                    upstream = repo.branches.local[name].upstream
                    if not upstream:
                        self._tracking.append("")
                    else:
                        self._tracking.append(upstream.shorthand)
                elif name.startswith(porcelain.REMOTES_PREFIX):
                    name = name.removeprefix(porcelain.REMOTES_PREFIX)
                    remote, name = porcelain.splitRemoteBranchShorthand(name)
                    try:
                        self._remoteBranchesDict[remote].append(name)
                    except KeyError:
                        print("Oops, missing remote:", remote)
                elif name.startswith(porcelain.TAGS_PREFIX):
                    name = name.removeprefix(porcelain.TAGS_PREFIX)
                    self._tags.append(name)

            # Sort remote branches
            for remote in self._remoteBranchesDict:
                self._remoteBranchesDict[remote] = sorted(self._remoteBranchesDict[remote])

        # HEAD
        with Benchmark("Sidebar/HEAD"):
            self._unbornHead = ""
            self._detachedHead = ""
            self._checkedOut = ""
            if repo.head_is_unborn:
                target: str = repo.lookup_reference("HEAD").target
                target = target.removeprefix("refs/heads/")
                self._unbornHead = target
            elif repo.head_is_detached:
                self._detachedHead = repo.head.target.hex
            else:
                self._checkedOut = repo.head.shorthand

        # Stashes
        with Benchmark("Sidebar/Stashes"):
            self._stashes = repo.listall_stashes()

        # Submodules
        with Benchmark("Sidebar/Submodules"):
            self._submodules = repo.listall_submodules()

        self._hiddenBranches = hiddenBranches

        self.endResetModel()

    def columnCount(self, parent: QModelIndex) -> int:
        return 1

    def index(self, row, column, parent: QModelIndex = None) -> QModelIndex:
        if not self.repo or column != 0 or row < 0:
            return QModelIndex()

        if not parent or not parent.isValid():  # root
            return self.createIndex(row, 0, HEADER_ITEMS[row].value)

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
            return self.createIndex(HEADER_ITEMS.index(parentHeader), 0, self.packId(parentHeader))

        if item in HEADER_ITEMS:
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

        if not parent.isValid():
            return len(HEADER_ITEMS)

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

    def data(self, index: QModelIndex, role: Qt.ItemDataRole = Qt.ItemDataRole.DisplayRole) -> Any:
        if not self.repo:
            return None

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
                if branchName == self._checkedOut:
                    return F"{ACTIVE_BULLET}{branchName}"
                else:
                    return branchName
            elif userRole:
                return branchName
            elif refRole:
                return F"refs/heads/{branchName}"
            elif toolTipRole:
                text = "<p style='white-space: pre'>"
                text += self.tr("Local branch <b>“{0}”</b>").format(escape(branchName))
                if branchName == self._checkedOut:
                    text += "\n" + ACTIVE_BULLET + self.tr("Active branch")
                if self._tracking[branchNo]:
                    text += "\n" + self.tr("Tracking remote branch “{0}”").format(escape(self._tracking[branchNo]))
                text += "<i/>"  # Force HTML
                return text
            elif hiddenRole:
                return F"refs/heads/{branchName}" in self._hiddenBranches
            elif fontRole:
                if F"refs/heads/{branchName}" in self._hiddenBranches:
                    return self.hiddenBranchFont()
                else:
                    return None

        elif item == EItem.UnbornHead:
            if displayRole:
                return F"{ACTIVE_BULLET}{self._unbornHead} " + self.tr("[unborn]")
            elif userRole:
                return self._unbornHead
            elif toolTipRole:
                return self.tr("Unborn HEAD: does not point to a commit yet.")
            elif hiddenRole:
                return False

        elif item == EItem.DetachedHead:
            if displayRole:
                return ACTIVE_BULLET + self.tr("[detached HEAD]")
            elif userRole:
                return self._detachedHead
            elif toolTipRole:
                return self.tr("Detached HEAD") + " @ " + self._detachedHead
            elif hiddenRole:
                return False
            elif role == decorationRole:
                if MACOS or WINDOWS:
                    return stockIcon(QStyle.StandardPixmap.SP_MessageBoxWarning)
                else:
                    return QIcon("assets:achtung.svg")

        elif item == EItem.Remote:
            if displayRole or userRole:
                return self._remotes[row]
            elif toolTipRole:
                return self._remoteURLs[row]
            elif hiddenRole:
                return False

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
                return F"{remoteName}/{branchName}"
            elif fontRole:
                if F"refs/remotes/{remoteName}/{branchName}" in self._hiddenBranches:
                    return self.hiddenBranchFont()
                else:
                    return None
            elif hiddenRole:
                return F"refs/remotes/{remoteName}/{branchName}" in self._hiddenBranches

        elif item == EItem.Tag:
            if displayRole or userRole:
                return self._tags[row]
            elif refRole:
                return F"refs/tags/{self._tags[row]}"
            elif hiddenRole:
                return False

        elif item == EItem.Stash:
            stash = self._stashes[row]
            if displayRole:
                return porcelain.getCoreStashMessage(stash.message)
            elif refRole:
                return F"stash@{{{row}}}"
            elif toolTipRole:
                return F"<b>stash@{{{row}}}</b>:<br/>{escape(stash.message)}"
            elif userRole:
                return stash.commit_id.hex
            elif hiddenRole:
                return False

        elif item == EItem.Submodule:
            if displayRole:
                return self._submodules[row].rsplit("/", 1)[-1]
            elif toolTipRole:
                return self._submodules[row]
            elif userRole:
                return self._submodules[row]
            elif hiddenRole:
                return False

        elif item == EItem.UncommittedChanges:
            if displayRole:
                return self.tr("Changes")
            elif refRole:
                # Return fake ref so we can select Uncommitted Changes from elsewhere
                return "UNCOMMITTED_CHANGES"
            elif fontRole:
                font = self._parentWidget.font()
                font.setBold(True)
                return font
            elif hiddenRole:
                return False

        else:
            if displayRole:
                ITEM_NAMES = {
                    EItem.UncommittedChanges: self.tr("Changes"),
                    EItem.LocalBranchesHeader: self.tr("Branches"),
                    EItem.StashesHeader: self.tr("Stashes"),
                    EItem.RemotesHeader: self.tr("Remotes"),
                    EItem.TagsHeader: self.tr("Tags"),
                    EItem.SubmodulesHeader: self.tr("Submodules"),
                    EItem.LocalBranch: self.tr("Local branch"),
                    EItem.DetachedHead: self.tr("Detached HEAD"),
                    EItem.UnbornHead: self.tr("Unborn HEAD"),
                    EItem.RemoteBranch: self.tr("Remote branch"),
                    EItem.Stash: self.tr("Stash"),
                    EItem.Remote: self.tr("Remote"),
                    EItem.Tag: self.tr("Tag"),
                    EItem.Submodule: self.tr("Submodules"),
                    EItem.Spacer: "---",
                }
                return ITEM_NAMES[item]
            elif refRole:
                return ""
            elif fontRole:
                font = self._parentWidget.font()
                font.setBold(True)
                return font
            elif hiddenRole:
                return False

        # fallback
        if sizeHintRole:
            return QSize(-1, self._parentWidget.fontMetrics().height())
        elif hiddenRole:
            return False

        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        item = self.unpackItem(index)

        if item == EItem.Spacer:
            return Qt.ItemFlag.NoItemFlags

        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
