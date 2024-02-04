from __future__ import annotations

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
BRANCH_FOLDERS = True


class SidebarTabMode(enum.IntEnum):
    NonModal = -1
    Branches = 0
    Stashes = 1
    Tags = 2
    Submodules = 3


class EItem(enum.IntEnum):
    Root = -1
    Spacer = 0
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
    RemoteBranchFolder = enum.auto()
    Tag = enum.auto()
    Submodule = enum.auto()


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
    EItem.RemoteBranchFolder: -1,
}

if MODAL_SIDEBAR: UNINDENT_ITEMS.update({
    EItem.LocalBranchesHeader: -1,
    EItem.RemotesHeader: -1,
    EItem.StashesHeader: -1,
    EItem.TagsHeader: -1,
    EItem.SubmodulesHeader: -1,
})


class SidebarNode:
    @staticmethod
    def fromIndex(index: QModelIndex) -> SidebarNode | None:
        if not index.isValid():
            return None
        p = index.internalPointer()
        assert isinstance(p, SidebarNode)
        return p

    def __init__(self, kind: EItem, data: str = ""):
        self.children = []
        self.parent = None
        self.row = -1
        self.kind = kind
        self.data = data

    def appendChild(self, node: SidebarNode):
        assert not node.parent
        assert self.kind not in LEAF_ITEMS
        node.row = len(self.children)
        node.parent = self
        self.children.append(node)

    def findChild(self, kind: EItem, data: str = "") -> SidebarNode:
        # TODO: Inefficient
        with suppress(StopIteration):
            return next(c for c in self.children if c.kind == kind and c.data == data)

    def __repr__(self):
        return f"SidebarNode({self.kind.name} {self.data})"


class SidebarModel(QAbstractItemModel):
    repoState: RepoState | None
    repo: Repo | None
    rootNode: SidebarNode
    nodesByRef: dict[str, SidebarNode]
    _unbornHead: str
    _detachedHead: str
    _checkedOut: str; "Shorthand of checked-out local branch"
    _checkedOutUpstream: str; "Shorthand of the checked-out branch's upstream"
    _stashes: list[Stash]
    _hiddenBranches: list[str]
    _hiddenStashCommits: list[str]
    _hideAllStashes: bool
    _hiddenRemotes: list[str]

    _cachedTooltipIndex: QModelIndex | None
    _cachedTooltipText: str

    modeId: int

    @staticmethod
    def getCollapseHash(index: QModelIndex):
        node = SidebarNode.fromIndex(index)
        return f"{node.kind}.{node.data}"
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
        self.rootNode = SidebarNode(EItem.Root)
        self.nodesByRef = {}
        self._unbornHead = ""
        self._detachedHead = ""
        self._checkedOut = ""
        self._checkedOutUpstream = ""
        self._stashes = []
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
        remoteBranchesDict = {}

        self.clear(emitSignals=False)
        self.repo = repo
        self.repoState = repoState
        self.nodesByRef = {}

        # Set up root nodes
        with Benchmark("Set up root nodes"):
            rootNode = SidebarNode(EItem.Root)
            for eitem in self.rootLayoutDef:
                rootNode.appendChild(SidebarNode(eitem))
            branchRoot = rootNode.findChild(EItem.LocalBranchesHeader)
            remoteRoot = rootNode.findChild(EItem.RemotesHeader)
            tagRoot = rootNode.findChild(EItem.TagsHeader)
            submoduleRoot = rootNode.findChild(EItem.SubmodulesHeader)
            stashRoot = rootNode.findChild(EItem.StashesHeader)
            self.rootNode = rootNode

        # Remote list
        with Benchmark("Remotes"):
            # RemoteCollection.names() is much faster than iterating on RemoteCollection itself
            for i, name in enumerate(repo.remotes.names()):
                remoteBranchesDict[name] = []
                node = SidebarNode(EItem.Remote, name)
                remoteRoot.appendChild(node)

        # Refs
        with Benchmark("Refs"):
            for name in reversed(refCache):  # reversed because refCache sorts tips by ASCENDING commit time
                prefix, shorthand = RefPrefix.split(name)

                if prefix == RefPrefix.HEADS:
                    node = SidebarNode(EItem.LocalBranch, name)
                    branchRoot.appendChild(node)
                    self.nodesByRef[name] = node
                    # We're not caching upstreams because it's very expensive to do

                elif prefix == RefPrefix.REMOTES:
                    remote, branchName = split_remote_branch_shorthand(shorthand)
                    try:
                        remoteBranchesDict[remote].append(branchName)
                    except KeyError:
                        logger.warning(f"Refresh cache: missing remote: {remote}")
                    # Remote branches are added later

                elif prefix == RefPrefix.TAGS:
                    node = SidebarNode(EItem.Tag, name)
                    tagRoot.appendChild(node)
                    self.nodesByRef[name] = node

                elif name == "HEAD" or name.startswith("stash@{"):
                    pass  # handled separately

                else:
                    logger.warning(f"Refresh cache: unsupported ref prefix: {name}")

            # Sort remote branches
            for remote in remoteBranchesDict:
                remoteNode = remoteRoot.findChild(EItem.Remote, remote)
                assert remoteNode is not None

                remoteBranchesDict[remote] = sorted(remoteBranchesDict[remote])

                if not BRANCH_FOLDERS:
                    for rb in remoteBranchesDict[remote]:
                        node = SidebarNode(EItem.RemoteBranch, RefPrefix.REMOTES + f"{remote}/{rb}")
                        remoteNode.appendChild(node)
                        self.nodesByRef[refName] = node
                else:
                    pFolder = ""
                    folderNode = remoteNode

                    for rb in remoteBranchesDict[remote]:
                        if "/" not in rb:
                            folderName = ""
                        else:
                            folderName, _ = rb.rsplit("/", 1)

                        if pFolder != folderName:
                            pFolder = folderName
                            if folderName:
                                assert (not settings.DEVDEBUG
                                        or not remoteNode.findChild(EItem.RemoteBranchFolder, folderName)), \
                                    "remote branch folder already created"
                                folderNode = SidebarNode(EItem.RemoteBranchFolder, folderName)
                                remoteNode.appendChild(folderNode)
                            else:
                                folderNode = remoteNode

                        if settings.DEVDEBUG:
                            if folderName:
                                assert folderNode is not remoteNode and folderNode.kind == EItem.RemoteBranchFolder and folderNode.data == folderName
                            else:
                                assert folderNode is remoteNode

                        refName = RefPrefix.REMOTES + f"{remote}/{rb}"
                        node = SidebarNode(EItem.RemoteBranch, refName)
                        folderNode.appendChild(node)
                        self.nodesByRef[refName] = node

        # HEAD
        # TODO: New model
        with Benchmark("HEAD"):
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
        with Benchmark("Stashes"):
            self._stashes = repo.listall_stashes()
            for i, stash in enumerate(self._stashes):
                refName = f"stash@{{{i}}}"
                node = SidebarNode(EItem.Stash, stash.commit_id.hex)
                stashRoot.appendChild(node)
                self.nodesByRef[refName] = node

        # Submodules
        with Benchmark("Submodules"):
            for submodule in repo.listall_submodules_fast():
                node = SidebarNode(EItem.Submodule, submodule)
                submoduleRoot.appendChild(node)

        self._hiddenBranches = repoState.uiPrefs.hiddenBranches
        self._hiddenStashCommits = repoState.uiPrefs.hiddenStashCommits
        self._hideAllStashes = repoState.uiPrefs.hideAllStashes
        self._hiddenRemotes = repoState.uiPrefs.hiddenRemotes

        with Benchmark("endResetModel" + ("[ModelTester might slow this down]" if settings.DEVDEBUG else "")):
            self.endResetModel()

    def index(self, row: int, column: int, parent: QModelIndex = None) -> QModelIndex:
        # Return an index given a parent and a row (i.e. child number within parent)

        # Illegal
        if column != 0 or row < 0:
            return QModelIndex()

        if not parent or not parent.isValid():
            parentNode = self.rootNode
        else:
            parentNode = SidebarNode.fromIndex(parent)

        childNode = parentNode.children[row]
        assert childNode.row == row

        return self.createIndex(row, 0, childNode)

    def parent(self, index: QModelIndex) -> QModelIndex:
        # Return the parent of the given index

        # No repo or root node: no parent
        if not index.isValid():
            return QModelIndex()

        # Get parent node
        node = SidebarNode.fromIndex(index)
        node = node.parent

        # Blank index for children of root node
        if node is self.rootNode:
            return QModelIndex()

        return self.createIndex(node.row, 0, node)

    """
    # What's the use of this if it works fine without?
    def hasChildren(self, parent: QModelIndex):
        if not parent.isValid():
            node = self.rootNode
        else:
            node = SidebarNode.fromIndex(parent)
        return len(node.children) >= 1
    """

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if not parent.isValid():  # root
            node = self.rootNode
        else:
            node = SidebarNode.fromIndex(parent)
        return len(node.children)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 1

    def hiddenBranchFont(self) -> QFont:
        font = self._parentWidget.font()
        font.setStrikeOut(True)
        return font

    def cacheTooltip(self, index: QModelIndex, text: str):
        self._cachedTooltipIndex = index
        self._cachedTooltipText = text

    def data(self, index: QModelIndex, role: Qt.ItemDataRole = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None

        # Tooltips may show information that is expensive to obtain.
        # Try to reuse any tooltip that we may have cached for the same index.
        if role == Qt.ItemDataRole.ToolTipRole and index == self._cachedTooltipIndex:
            return self._cachedTooltipText

        node = SidebarNode.fromIndex(index)

        displayRole = role == Qt.ItemDataRole.DisplayRole
        toolTipRole = role == Qt.ItemDataRole.ToolTipRole
        sizeHintRole = role == Qt.ItemDataRole.SizeHintRole
        fontRole = role == Qt.ItemDataRole.FontRole
        decorationRole = role == Qt.ItemDataRole.DecorationRole
        userRole = role == ROLE_USERDATA
        hiddenRole = role == ROLE_ISHIDDEN
        refRole = role == ROLE_REF

        row = index.row()
        item = node.kind

        if role == ROLE_EITEM:  # for testing (match by EItem type)
            return item.value

        if item == EItem.Spacer:
            if sizeHintRole:
                # Note: If uniform row heights are on, this won't actually be effective
                # (unless the Spacer is the first item, in which case all other rows will be short)
                parentWidget: QWidget = QObject.parent(self)
                return QSize(-1, int(0.5 * parentWidget.fontMetrics().height()))
            else:
                return None

        elif item == EItem.LocalBranch:
            refName = node.data
            branchName = refName.removeprefix(RefPrefix.HEADS)
            if displayRole:
                return branchName
            elif userRole:
                return branchName
            elif refRole:
                return refName
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
                return refName in self._hiddenBranches
            elif fontRole:
                if refName in self._hiddenBranches:
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
            remoteName = node.data
            if displayRole or userRole:
                return remoteName
            elif toolTipRole:
                url = self.repo.remotes[remoteName].url
                return "<p style='white-space: pre'>" + escape(url)
            elif fontRole:
                if remoteName in self._hiddenRemotes:
                    return self.hiddenBranchFont()
            elif hiddenRole:
                return False
            elif decorationRole:
                return stockIcon("git-remote")

        elif item == EItem.RemoteBranch:
            refName = node.data
            shorthand = refName.removeprefix(RefPrefix.REMOTES)
            remoteName, branchName = split_remote_branch_shorthand(shorthand)
            if displayRole:
                return branchName.rsplit("/", 1)[-1]
            elif refRole:
                return refName
            elif userRole:
                return shorthand
            elif toolTipRole:
                text = "<p style='white-space: pre'>"
                text += self.tr("Remote-tracking branch {0}").format(bquo(shorthand))
                if self._checkedOutUpstream == shorthand:
                    text += ("<br><i>" + self.tr("This is the upstream for the checked-out branch ({0}).")
                             ).format(hquoe(self._checkedOut))
                return text
            elif fontRole:
                if refName in self._hiddenBranches:
                    return self.hiddenBranchFont()
                elif self._checkedOutUpstream == shorthand:
                    font = QFont(self._parentWidget.font())
                    font.setItalic(True)
                    font.setWeight(QFont.Weight.Medium)
                    return font
                else:
                    return None
            elif hiddenRole:
                return refName in self._hiddenBranches
            elif decorationRole:
                return stockIcon("git-branch")

        elif item == EItem.RemoteBranchFolder:
            if displayRole:
                return node.data
            elif decorationRole:
                return stockIcon("git-folder")

        elif item == EItem.Tag:
            if displayRole or userRole:
                return node.data.removeprefix(RefPrefix.TAGS)
            elif refRole:
                return node.data
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
                return node.data.rsplit("/", 1)[-1]
            elif toolTipRole:
                return node.data
            elif userRole:
                return node.data
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
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags

        node = SidebarNode.fromIndex(index)
        item = node.kind

        if item == EItem.Spacer:
            return Qt.ItemFlag.ItemNeverHasChildren

        if item in ALWAYS_EXPAND:
            return Qt.ItemFlag.NoItemFlags

        f = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

        if item in LEAF_ITEMS:
            assert not node.children
            f |= Qt.ItemFlag.ItemNeverHasChildren

        return f
