from __future__ import annotations

from contextlib import suppress
import logging
import enum
from typing import Any, Iterable

from gitfourchette import settings
from gitfourchette.porcelain import *
from gitfourchette.qt import *
from gitfourchette.toolbox import *
from gitfourchette.trtables import TrTables
from gitfourchette.repomodel import RepoModel

logger = logging.getLogger(__name__)

BRANCH_FOLDERS = True

UC_FAKEREF = "UC_FAKEREF"  # actual refs are either HEAD or they start with /refs/, so this name is safe
"Fake reference for Uncommitted Changes."


class EItem(enum.IntEnum):
    Root = -1
    Spacer = 0
    WorkdirHeader = enum.auto()
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
    RefFolder = enum.auto()


HEADER_ITEMS = [
    EItem.WorkdirHeader,
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
# HEADER_ITEMS = [i for i in HEADER_ITEMS if i != EItem.Spacer]

FORCE_EXPAND = [
    EItem.WorkdirHeader
]
""" SidebarNode kinds to always expand (in modal sidebars only) """

NONLEAF_ITEMS = sorted([
    EItem.Root,
    EItem.WorkdirHeader,
    EItem.LocalBranchesHeader,
    EItem.RefFolder,
    EItem.Remote,
    EItem.RemotesHeader,
    EItem.StashesHeader,
    EItem.SubmodulesHeader,
    EItem.TagsHeader,
])

UNINDENT_ITEMS = {
    EItem.LocalBranch: -1,
    EItem.UnbornHead: -1,
    EItem.DetachedHead: -1,
    EItem.Stash: -1,
    EItem.Tag: -1,
    EItem.Submodule: -1,
    EItem.Remote: -1,
    EItem.RemoteBranch: -1,
    EItem.RefFolder: -1,
}

HIDEABLE_ITEMS = sorted([
    EItem.LocalBranch,
    EItem.Remote,
    EItem.RemoteBranch,
    EItem.RefFolder,
])


class SidebarNode:
    children: list[SidebarNode]
    parent: SidebarNode | None
    row: int
    kind: EItem
    data: str
    warning: str
    displayName: str

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
        self.warning = ""
        self.displayName = ""

    def appendChild(self, node: SidebarNode):
        assert self.mayHaveChildren()
        assert self is not node
        assert not node.parent
        node.row = len(self.children)
        node.parent = self
        self.children.append(node)

    def findChild(self, kind: EItem, data: str = "") -> SidebarNode:
        """ Warning: this is inefficient - don't use this if there are many children! """
        assert self.mayHaveChildren()
        with suppress(StopIteration):
            return next(c for c in self.children if c.kind == kind and c.data == data)

    def createIndex(self, model: QAbstractItemModel) -> QModelIndex:
        return model.createIndex(self.row, 0, self)

    def getCollapseHash(self) -> str:
        assert self.mayHaveChildren(), "it's futile to hash a leaf"
        return f"{self.kind.name}.{self.data}"
        # Warning: it's tempting to replace this with something like "hash(data) << 8 | item",
        # but hash(data) doesn't return stable values across different Python sessions,
        # so it's not suitable for persistent storage (in history.json).

    def mayHaveChildren(self):
        return self.kind in NONLEAF_ITEMS

    def wantForceExpand(self):
        return self.kind in FORCE_EXPAND

    def canBeHidden(self):
        return self.kind in HIDEABLE_ITEMS

    def walk(self):
        frontier = self.children[:]
        while frontier:
            node = frontier.pop()
            yield node
            frontier.extend(node.children)

    def isSimilarEnoughTo(self, other: SidebarNode):
        """ Use this to compare SidebarNodes from two different models. """
        return self.kind == other.kind and self.data == other.data

    def __repr__(self):
        return f"SidebarNode({self.kind.name} {self.data})"


class SidebarModel(QAbstractItemModel):
    repoModel: RepoModel | None
    rootNode: SidebarNode
    nodesByRef: dict[str, SidebarNode]
    _unbornHead: str
    _checkedOut: str; "Shorthand of checked-out local branch"
    _checkedOutUpstream: str; "Shorthand of the checked-out branch's upstream"

    _cachedTooltipIndex: QModelIndex | None
    _cachedTooltipText: str

    collapseCache: set[str]
    collapseCacheValid: bool

    class Role:
        Ref = Qt.ItemDataRole.UserRole + 0
        Hidden = Qt.ItemDataRole.UserRole + 1
        IconKey = Qt.ItemDataRole.UserRole + 2

    @property
    def _parentWidget(self) -> QWidget:
        return QObject.parent(self)

    @property
    def repo(self):
        return self.repoModel.repo

    def __init__(self, parent=None):
        super().__init__(parent)
        self.clear()

        if settings.DEVDEBUG and QAbstractItemModelTester is not None:
            self.modelTester = QAbstractItemModelTester(self)
            logger.warning("Sidebar model tester enabled. This will SIGNIFICANTLY slow down SidebarModel.rebuild!")

    def clear(self, emitSignals=True):
        if emitSignals:
            self.beginResetModel()

        self.repoModel = None
        self.rootNode = SidebarNode(EItem.Root)
        self.nodesByRef = {}
        self._checkedOut = ""
        self._checkedOutUpstream = ""

        self._cachedTooltipIndex = None
        self._cachedTooltipText = ""

        self.collapseCache = set()
        self.collapseCacheValid = False

        if emitSignals:
            self.endResetModel()

    def isExplicitlyHidden(self, node: SidebarNode) -> bool:
        if node.kind == EItem.LocalBranch or node.kind == EItem.RemoteBranch:
            return node.data in self.repoModel.prefs.hiddenRefPatterns
        elif node.kind == EItem.Remote:
            return f"{RefPrefix.REMOTES}{node.data}/" in self.repoModel.prefs.hiddenRefPatterns
        elif node.kind == EItem.RefFolder:
            return f"{node.data}/" in self.repoModel.prefs.hiddenRefPatterns
        else:
            return False

    def isImplicitlyHidden(self, node: SidebarNode) -> bool:
        if node.kind == EItem.LocalBranch or node.kind == EItem.RemoteBranch:
            return node.data in self.repoModel.hiddenRefs and node.data not in self.repoModel.prefs.hiddenRefPatterns
        else:
            return False

    def isAncestryChainExpanded(self, node: SidebarNode):
        # Assume everything is expanded if collapse cache is missing (see restoreExpandedItems).
        if not self.collapseCacheValid:
            return True

        # My collapsed state doesn't matter here - it only affects my children.
        # So start looking at my parent.
        node = node.parent

        # Walk up parent chain until root index (row -1)
        while node.parent is not None:
            h = node.getCollapseHash()
            if h in self.collapseCache:
                return False
            node = node.parent

        return True

    def onIndexExpanded(self, index: QModelIndex):
        node = SidebarNode.fromIndex(index)
        h = node.getCollapseHash()
        self.collapseCache.discard(h)

    def onIndexCollapsed(self, index: QModelIndex):
        node = SidebarNode.fromIndex(index)
        h = node.getCollapseHash()
        self.collapseCache.add(h)

    def refreshRepoName(self):
        if self.rootNode and self.repoModel:
            workdirNode = self.rootNode.findChild(EItem.WorkdirHeader)
            workdirNode.displayName = settings.history.getRepoNickname(self.repo.workdir)

    @benchmark
    def rebuild(self, repoModel: RepoModel):
        self.beginResetModel()

        repo = repoModel.repo

        self.clear(emitSignals=False)
        self.repoModel = repoModel
        self.nodesByRef = {}

        # Pending ref shorthands for _makeRefTreeNodes
        localBranches = []
        remoteBranchesDict = {}
        tags = []

        # -----------------------------
        # Set up root nodes
        # -----------------------------
        rootNode = SidebarNode(EItem.Root)
        for eitem in HEADER_ITEMS:
            rootNode.appendChild(SidebarNode(eitem))
        uncommittedNode = rootNode.findChild(EItem.UncommittedChanges)
        branchRoot = rootNode.findChild(EItem.LocalBranchesHeader)
        remoteRoot = rootNode.findChild(EItem.RemotesHeader)
        tagRoot = rootNode.findChild(EItem.TagsHeader)
        submoduleRoot = rootNode.findChild(EItem.SubmodulesHeader)
        stashRoot = rootNode.findChild(EItem.StashesHeader)

        self.rootNode = rootNode
        self.nodesByRef[UC_FAKEREF] = uncommittedNode

        self.refreshRepoName()

        # -----------------------------
        # HEAD
        # -----------------------------
        try:
            # Try to get the name of the checked-out branch
            checkedOut = repo.head.name

        except GitError:
            # Unborn HEAD - Get name of unborn branch
            assert repo.head_is_unborn
            target: str = repo.lookup_reference("HEAD").target
            target = target.removeprefix(RefPrefix.HEADS)
            node = SidebarNode(EItem.UnbornHead, target)
            branchRoot.appendChild(node)
            self.nodesByRef["HEAD"] = node

        else:
            # It's not unborn
            if checkedOut == 'HEAD':
                # Detached head, leave self._checkedOut blank
                assert repo.head_is_detached
                node = SidebarNode(EItem.DetachedHead, str(repo.head.target))
                branchRoot.appendChild(node)
                self.nodesByRef["HEAD"] = node

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

        # -----------------------------
        # Remotes
        # -----------------------------
        for name in repoModel.remotes:
            remoteBranchesDict[name] = []
            node = SidebarNode(EItem.Remote, name)
            remoteRoot.appendChild(node)

        # -----------------------------
        # Refs
        # -----------------------------
        for name in reversed(repoModel.refs):  # reversed because refCache sorts tips by ASCENDING commit time
            prefix, shorthand = RefPrefix.split(name)

            if prefix == RefPrefix.HEADS:
                localBranches.append(shorthand)
                # We're not caching upstreams because it's very expensive to do

            elif prefix == RefPrefix.REMOTES:
                remote, branchName = split_remote_branch_shorthand(shorthand)
                try:
                    remoteBranchesDict[remote].append(branchName)
                except KeyError:
                    logger.warning(f"Refresh cache: missing remote: {remote}")

            elif prefix == RefPrefix.TAGS:
                tags.append(shorthand)

            elif name == "HEAD" or name.startswith("stash@{"):
                pass  # handled separately

            else:
                logger.warning(f"Refresh cache: unsupported ref prefix: {name}")

        # Populate local branch tree
        self.populateRefNodeTree(localBranches, branchRoot, EItem.LocalBranch, RefPrefix.HEADS)

        # Populate tag tree
        self.populateRefNodeTree(tags, tagRoot, EItem.Tag, RefPrefix.TAGS)

        # Populate remote tree
        for remote, branches in remoteBranchesDict.items():
            remoteNode = remoteRoot.findChild(EItem.Remote, remote)
            assert remoteNode is not None
            branches.sort(key=str.lower)  # Sort remote branches
            self.populateRefNodeTree(branches, remoteNode, EItem.RemoteBranch, f"{RefPrefix.REMOTES}{remote}/")

        # -----------------------------
        # Stashes
        # -----------------------------
        for i, stashCommitId in enumerate(repoModel.stashes):
            message = repo[stashCommitId].message
            message = strip_stash_message(message)
            refName = f"stash@{{{i}}}"
            node = SidebarNode(EItem.Stash, str(stashCommitId))
            node.displayName = message
            stashRoot.appendChild(node)
            self.nodesByRef[refName] = node

        # -----------------------------
        # Submodules
        # -----------------------------
        for submoduleKey, submodulePath in repoModel.submodules.items():
            node = SidebarNode(EItem.Submodule, submoduleKey)
            submoduleRoot.appendChild(node)

            if not repo.submodule_dotgit_present(submodulePath):
                node.warning = self.tr("Submodule not initialized.")

        # -----------------------------
        # Commit new model
        # -----------------------------
        self.endResetModel()

    def populateRefNodeTree(self, shorthands: list[str], containerNode: SidebarNode, kind: EItem, refNamePrefix: str):
        pendingFolders = {}

        for b in shorthands:
            if not BRANCH_FOLDERS or "/" not in b:
                folderNode = containerNode
            else:
                folderName = b.rsplit("/", 1)[0]
                try:
                    folderNode = pendingFolders[folderName]
                except KeyError:
                    # Create node for folder, but add it to containerNode later
                    # so that all folders are grouped together.
                    folderNode = SidebarNode(EItem.RefFolder, refNamePrefix + folderName)
                    pendingFolders[folderName] = folderNode

            refName = refNamePrefix + b
            node = SidebarNode(kind, refName)
            folderNode.appendChild(node)
            self.nodesByRef[refName] = node

        for folderName, folderNode in pendingFolders.items():
            parts = folderName.split("/")
            parts.pop()
            while parts:
                parentFolder = "/".join(parts)
                try:
                    parentNode = pendingFolders[parentFolder]
                    parentNode.appendChild(folderNode)
                    folderNode.displayName = folderNode.data.removeprefix(parentNode.data)
                    break
                except KeyError:
                    parts.pop()
            else:
                folderNode.displayName = RefPrefix.split(folderNode.data)[1]
                containerNode.appendChild(folderNode)

    def index(self, row: int, column: int, parent: QModelIndex = None) -> QModelIndex:
        # Return an index given a parent and a row (i.e. child number within parent)

        # Illegal
        if column != 0 or row < 0:
            return QModelIndex()

        if not parent or not parent.isValid():
            parentNode = self.rootNode
        else:
            parentNode = SidebarNode.fromIndex(parent)

        node = parentNode.children[row]
        assert node.row == row

        return node.createIndex(self)

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

        return node.createIndex(self)

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
        hiddenRole = role == SidebarModel.Role.Hidden
        refRole = role == SidebarModel.Role.Ref
        iconKeyRole = role == SidebarModel.Role.IconKey

        row = index.row()
        item = node.kind

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
                if BRANCH_FOLDERS:
                    return branchName.rsplit("/", 1)[-1]
                else:
                    return branchName
            elif refRole:
                return refName
            elif toolTipRole:
                text = "<p style='white-space: pre'>"
                text += self.tr("{0} (local branch)").format(btag(branchName))
                # Try to get the upstream (branch.upstream_name raises KeyError if there isn't one)
                # Warning: branch.upstream_name can be a bit expensive
                with suppress(KeyError):
                    branch = self.repo.branches.local[branchName]
                    upstream = branch.upstream_name.removeprefix(RefPrefix.REMOTES)
                    text += "\n" + self.tr("Upstream: {0}").format(escape(upstream))
                if branchName == self._checkedOut:
                    text += "\n<img src='assets:icons/git-head' style='vertical-align: bottom;'/> "
                    text += "HEAD " + self.tr("(this is the checked-out branch)")
                self.cacheTooltip(index, text)
                return text
            elif hiddenRole:
                return self.isExplicitlyHidden(node)
            elif iconKeyRole:
                return "git-branch" if branchName != self._checkedOut else "git-head"

        elif item == EItem.UnbornHead:
            target = node.data
            if displayRole:
                return self.tr("[unborn]") + " " + target
            elif toolTipRole:
                text = ("<p style='white-space: pre'>"
                        + self.tr("Unborn HEAD: does not point to a commit yet.") + "\n"
                        + self.tr("Local branch {0} will be created when you create the initial commit.")
                        ).format(bquo(target))
                self.cacheTooltip(index, text)
                return text
            elif hiddenRole:
                return False

        elif item == EItem.DetachedHead:
            if displayRole:
                return self.tr("Detached HEAD")
            elif toolTipRole:
                oid = Oid(hex=node.data)
                caption = self.tr("Detached HEAD")
                return f"<p style='white-space: pre'>{caption} @ {shortHash(oid)}"
            elif hiddenRole:
                return False
            elif refRole:
                return "HEAD"
            elif iconKeyRole:
                return "achtung"

        elif item == EItem.Remote:
            remoteName = node.data
            if displayRole:
                return remoteName
            elif toolTipRole:
                url = self.repo.remotes[remoteName].url
                return "<p style='white-space: pre'>" + escape(url)
            elif hiddenRole:
                return False
            elif iconKeyRole:
                return "git-remote"

        elif item == EItem.RemoteBranch:
            refName = node.data
            shorthand = refName.removeprefix(RefPrefix.REMOTES)
            remoteName, branchName = split_remote_branch_shorthand(shorthand)
            if displayRole:
                if BRANCH_FOLDERS:
                    return branchName.rsplit("/", 1)[-1]
                else:
                    return branchName
            elif refRole:
                return refName
            elif toolTipRole:
                text = "<p style='white-space: pre'>"
                text += self.tr("{0} (remote-tracking branch)").format(btag(shorthand))
                if self._checkedOutUpstream == shorthand:
                    text += ("<br><i>" + self.tr("Upstream for the checked-out branch ({0})")
                             ).format(hquoe(self._checkedOut))
                return text
            elif fontRole:
                if self._checkedOutUpstream == shorthand:
                    font = QFont(self._parentWidget.font())
                    font.setItalic(True)
                    return font
                else:
                    return None
            elif hiddenRole:
                return self.isExplicitlyHidden(node)
            elif iconKeyRole:
                return "git-branch"

        elif item == EItem.RefFolder:
            refName = node.data
            if displayRole:
                return node.displayName
            elif toolTipRole:
                prefix, name = RefPrefix.split(refName)
                text = "<p style='white-space: pre'>"
                text += "<img src='assets:icons/git-folder' style='vertical-align: bottom;'/> "
                if prefix == RefPrefix.REMOTES:
                    text += self.tr("{0} (remote branch folder)").format(btag(name))
                elif prefix == RefPrefix.TAGS:
                    text += self.tr("{0} (tag folder)").format(btag(name))
                else:
                    text += self.tr("{0} (local branch folder)").format(btag(name))
                return text
            elif hiddenRole:
                return self.isExplicitlyHidden(node)
            elif iconKeyRole:
                return "git-folder"

        elif item == EItem.Tag:
            refName = node.data
            tagName = refName.removeprefix(RefPrefix.TAGS)
            if displayRole:
                if BRANCH_FOLDERS:
                    return tagName.rsplit("/", 1)[-1]
                else:
                    return tagName
            elif refRole:
                return refName
            elif toolTipRole:
                text = "<p style='white-space: pre'>"
                text += self.tr("Tag {0}").format(bquo(tagName))
                return text
            elif hiddenRole:
                return False
            elif iconKeyRole:
                return "git-tag"

        elif item == EItem.Stash:
            if displayRole:
                return node.displayName
            elif refRole:
                return F"stash@{{{row}}}"
            elif toolTipRole:
                oid = Oid(hex=node.data)
                commit = self.repo.peel_commit(oid)
                commitQdt = QDateTime.fromSecsSinceEpoch(commit.commit_time, Qt.TimeSpec.OffsetFromUTC, commit.commit_time_offset * 60)
                commitTimeStr = QLocale().toString(commitQdt, settings.prefs.shortTimeFormat)
                text = "<p style='white-space: pre'>"
                text += f"<b>stash@{{{row}}}</b>: {escape(commit.message)}<br/>"
                text += f"<b>{self.tr('date:')}</b> {commitTimeStr}"
                self.cacheTooltip(index, text)
                return text
            elif hiddenRole:
                self.isExplicitlyHidden(node)
            elif iconKeyRole:
                return "git-stash"

        elif item == EItem.Submodule:
            if displayRole:
                return node.data.rsplit("/", 1)[-1]
            elif toolTipRole:
                text = "<p style='white-space: pre'>"
                text += self.tr("{0} (submodule)").format(f"<b>{escape(node.data)}</b>")
                text += "\n" + self.tr("Workdir: {0}").format(escape(self.repo.listall_submodules_dict()[node.data]))
                url = self.repo.submodules[node.data].url or self.tr("[not set]")
                text += "\n" + self.tr("URL: {0}").format(escape(url))
                if node.warning:
                    text += "<br>\u26a0 " + node.warning
                return text
            elif hiddenRole:
                return False
            elif iconKeyRole:
                return "achtung" if node.warning else "git-submodule"

        elif item == EItem.UncommittedChanges:
            if displayRole:
                changesText = TrTables.sidebarItem(EItem.UncommittedChanges)
                numUncommittedChanges = self.repoModel.numUncommittedChanges
                if numUncommittedChanges != 0:
                    ucSuffix = f" ({numUncommittedChanges})"
                    changesText = changesText.replace("", ucSuffix + "") + ucSuffix
                return changesText
            elif refRole:
                # Return fake ref so we can select Uncommitted Changes from elsewhere
                return UC_FAKEREF
            elif hiddenRole:
                return False
            elif iconKeyRole:
                return "git-workdir"
            elif toolTipRole:
                return appendShortcutToToolTipText(self.tr("Go to Uncommitted Changes"), QKeySequence("Ctrl+U"))

        else:
            if displayRole:
                if item == EItem.WorkdirHeader:
                    return node.displayName
                elif item == EItem.LocalBranchesHeader:
                    return TrTables.sidebarItem(item)
                else:
                    name = TrTables.sidebarItem(item)
                    if node.getCollapseHash() in self.collapseCache:
                        name += f" ({len(node.children)})"
                    return name
            elif refRole:
                return ""
            elif fontRole:
                font = self._parentWidget.font()
                font.setWeight(QFont.Weight.DemiBold)
                return font
            elif hiddenRole:
                return False

        # fallback
        if sizeHintRole:
            return QSize(-1, int(1.2 * self._parentWidget.fontMetrics().height()))
        elif hiddenRole:
            return False

        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags

        node = SidebarNode.fromIndex(index)

        if node.kind == EItem.Spacer:
            return Qt.ItemFlag.ItemNeverHasChildren

        if node.kind in FORCE_EXPAND:
            return Qt.ItemFlag.NoItemFlags

        f = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

        if not node.mayHaveChildren():
            assert not node.children
            f |= Qt.ItemFlag.ItemNeverHasChildren

        return f
