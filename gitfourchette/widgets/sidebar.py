from gitfourchette import porcelain
from gitfourchette.actiondef import ActionDef
from gitfourchette.benchmark import Benchmark
from gitfourchette.globalshortcuts import GlobalShortcuts
from gitfourchette.qt import *
from gitfourchette.repostate import RepoState
from gitfourchette.util import elide, escamp, stockIcon
from html import escape
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
        self.repo = None

    def refreshCache(self, repo: pygit2.Repository, hiddenBranches: list[str], refCache: Iterable[str]):
        self.beginResetModel()

        self.repo = repo

        self._localBranches = []
        self._tracking = []
        self._tags = []
        self._remotes = []
        self._remoteURLs = []
        self._remoteBranchesDict = {}

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
                    self._remoteBranchesDict[remote].append(name)
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


class SidebarDelegate(QStyledItemDelegate):
    def __init__(self, parent: QWidget):
        super().__init__(parent)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        """
        Draw custom branch indicator. The standard one is too cluttered in some
        themes, e.g. Breeze, so I've disabled it in style.qss.
        
        In the macOS theme, the default actually looks fine... but let's
        override it anyway for consistency with other platforms.
        """

        view: QTreeView = option.widget
        item = SidebarModel.unpackItem(index)

        # Don't draw spacers at all (Windows theme has mouse hover effect by default)
        if item == EItem.Spacer:
            return

        opt = QStyleOptionViewItem(option)

        if item in UNINDENT_ITEMS:
            opt.rect.adjust(-view.indentation(), 0, 0, 0)

        if item not in LEAF_ITEMS:
            opt2 = QStyleOptionViewItem(option)

            r: QRect = opt2.rect

            # These metrics are a good compromise for Breeze, macOS, and Fusion.
            r.adjust(-view.indentation() * 6//10, 0, 0, 0)  # args must be integers for pyqt5!
            r.setWidth(6)

            # See QTreeView::drawBranches() in qtreeview.cpp for other interesting states
            opt2.state &= ~QStyle.StateFlag.State_MouseOver

            style: QStyle = view.style()
            arrowPrimitive = QStyle.PrimitiveElement.PE_IndicatorArrowDown if view.isExpanded(index) else QStyle.PrimitiveElement.PE_IndicatorArrowRight
            style.drawPrimitive(arrowPrimitive, opt2, painter, view)

        super().paint(painter, opt, index)


class Sidebar(QTreeView):
    uncommittedChangesClicked = Signal()
    refClicked = Signal(str)
    commitClicked = Signal(pygit2.Oid)

    newBranch = Signal()
    newBranchFromLocalBranch = Signal(str)
    renameBranch = Signal(str)
    deleteBranch = Signal(str)
    switchToBranch = Signal(str, bool)  # bool: ask for confirmation before switching
    mergeBranchIntoActive = Signal(str)
    rebaseActiveOntoBranch = Signal(str)
    pushBranch = Signal(str)
    fastForwardBranch = Signal(str)
    toggleHideBranch = Signal(str)
    newTrackingBranch = Signal(str)
    fetchRemoteBranch = Signal(str)
    renameRemoteBranch = Signal(str)
    deleteRemoteBranch = Signal(str)
    editTrackingBranch = Signal(str)
    commitChanges = Signal()
    amendChanges = Signal()
    exportWorkdirAsPatch = Signal()

    newRemote = Signal()
    fetchRemote = Signal(str)
    editRemote = Signal(str)
    deleteRemote = Signal(str)

    newStash = Signal()
    applyStash = Signal(pygit2.Oid)
    exportStashAsPatch = Signal(pygit2.Oid)
    dropStash = Signal(pygit2.Oid)

    openSubmoduleRepo = Signal(str)
    openSubmoduleFolder = Signal(str)

    def __init__(self, parent):
        super().__init__(parent)

        self.setObjectName("sidebar")  # for styling
        self.setMinimumWidth(128)
        self.setIndentation(16)
        self.setHeaderHidden(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.customContextMenuRequested.connect(self.onCustomContextMenuRequested)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        self.setItemDelegate(SidebarDelegate(self))

        self.setModel(SidebarModel(self))

        self.setAnimated(True)
        self.setUniformRowHeights(True)  # large sidebars update twice as fast with this, but we can't have thin spacers

    def updateHiddenBranches(self, hiddenBranches: list[str]):
        self.model().updateHiddenBranches(hiddenBranches)

    def generateMenuForEntry(self, item: EItem, data: str = "", menu: QMenu = None, index: QModelIndex = None):
        if menu is None:
            menu = QMenu(self)
            menu.setObjectName("SidebarContextMenu")

        actions = []

        if item == EItem.UncommittedChanges:
            actions += [
                ActionDef(self.tr("&Commit Staged Changes..."), self.commitChanges, shortcuts=GlobalShortcuts.commit),
                ActionDef(self.tr("&Amend Last Commit..."), self.amendChanges, shortcuts=GlobalShortcuts.amendCommit),
                ActionDef.SEPARATOR,
                ActionDef(self.tr("&Stash Uncommitted Changes..."), self.newStash, shortcuts=GlobalShortcuts.newStash),
                ActionDef(self.tr("E&xport Uncommitted Changes As Patch..."), self.exportWorkdirAsPatch),
            ]

        elif item == EItem.LocalBranchesHeader:
            actions += [
                ActionDef(self.tr("&New Branch..."), lambda: self.newBranch.emit(), shortcuts=GlobalShortcuts.newBranch),
            ]

        elif item == EItem.LocalBranch:
            fontMetrics = menu.fontMetrics()

            model: SidebarModel = self.model()
            repo = model.repo
            branch = repo.branches.local[data]

            activeBranchName = porcelain.getActiveBranchShorthand(repo)
            isCurrentBranch = branch and branch.is_checked_out()
            hasUpstream = bool(branch.upstream)
            upstreamBranchName = ""
            if branch.upstream:
                upstreamBranchName = branch.upstream.shorthand

            isBranchHidden = False
            if index:  # in test mode, we may not have an index
                isBranchHidden = self.model().data(index, ROLE_ISHIDDEN)

            thisBranchDisplay = elide(data)
            activeBranchDisplay = elide(activeBranchName)
            upstreamBranchDisplay = elide(upstreamBranchName)

            actions += [
                ActionDef(self.tr("&Switch to “{0}”").format(thisBranchDisplay),
                          lambda: self.switchToBranch.emit(data, False),  # False: don't ask for confirmation
                          "document-swap",
                          enabled=not isCurrentBranch),

                ActionDef.SEPARATOR,

                ActionDef(self.tr("&Merge “{0}” into “{1}”...").format(thisBranchDisplay, activeBranchDisplay),
                          lambda: self.mergeBranchIntoActive.emit(data),
                          enabled=not isCurrentBranch and activeBranchName),

                ActionDef(self.tr("&Rebase “{0}” onto “{1}”...").format(activeBranchDisplay, thisBranchDisplay),
                          lambda: self.rebaseActiveOntoBranch.emit(data),
                          enabled=not isCurrentBranch and activeBranchName),

                ActionDef.SEPARATOR,

                ActionDef(self.tr("&Push..."),
                          lambda: self.pushBranch.emit(data),
                          "vcs-push",
                          shortcuts=GlobalShortcuts.pushBranch),

                ActionDef(self.tr("&Fetch..."),
                          lambda: self.fetchRemoteBranch.emit(branch.upstream.shorthand),
                          QStyle.StandardPixmap.SP_BrowserReload,
                          enabled=hasUpstream),

                ActionDef(self.tr("Fast-Forward to “{0}”...").format(upstreamBranchDisplay)
                          if upstreamBranchName else self.tr("Fast-Forward..."),
                          lambda: self.fastForwardBranch.emit(data),
                          "vcs-pull",
                          enabled=hasUpstream,
                          shortcuts=GlobalShortcuts.pullBranch),

                ActionDef(self.tr("Set &Tracked Branch..."),
                          lambda: self.editTrackingBranch.emit(data)),

                ActionDef.SEPARATOR,

                ActionDef(self.tr("Re&name..."),
                          lambda: self.renameBranch.emit(data)),

                ActionDef(self.tr("&Delete..."),
                          lambda: self.deleteBranch.emit(data),
                          "vcs-branch-delete"),

                ActionDef.SEPARATOR,

                ActionDef(self.tr("New &Branch from Here..."),
                          lambda: self.newBranchFromLocalBranch.emit(data),
                          "vcs-branch"),

                ActionDef.SEPARATOR,

                ActionDef(self.tr("&Hide in graph"),
                          lambda: self.toggleHideBranch.emit("refs/heads/" + data),
                          checkState=1 if isBranchHidden else -1),
            ]

        elif item == EItem.DetachedHead:
            actions += [
                ActionDef(self.tr("New &Branch from Here..."),
                          lambda: self.newBranch.emit(),
                          "vcs-branch",
                          shortcuts=GlobalShortcuts.newBranch),
            ]

        elif item == EItem.RemoteBranch:
            isBranchHidden = False
            if index:  # in test mode, we may not have an index
                isBranchHidden = self.model().data(index, ROLE_ISHIDDEN)

            actions += [
                ActionDef(self.tr("New local branch tracking “{0}”...").format(escamp(elide(data))),
                          lambda: self.newTrackingBranch.emit(data),
                          "vcs-branch"),

                ActionDef(self.tr("Fetch this remote branch..."),
                          lambda: self.fetchRemoteBranch.emit(data),
                          QStyle.StandardPixmap.SP_BrowserReload),

                ActionDef.SEPARATOR,

                ActionDef(self.tr("Rename branch on remote..."),
                          lambda: self.renameRemoteBranch.emit(data)),

                ActionDef(self.tr("Delete branch on remote..."),
                          lambda: self.deleteRemoteBranch.emit(data),
                          QStyle.StandardPixmap.SP_TrashIcon),

                ActionDef.SEPARATOR,

                ActionDef(self.tr("&Hide in graph"),
                          lambda: self.toggleHideBranch.emit("refs/remotes/" + data),
                          checkState=1 if isBranchHidden else -1),
            ]

        elif item == EItem.Remote:
            actions += [
                ActionDef(self.tr("&Edit Remote..."),
                          lambda: self.editRemote.emit(data),
                          "document-edit"),

                ActionDef(self.tr("&Fetch all branches on this remote..."),
                          lambda: self.fetchRemote.emit(data),
                          QStyle.StandardPixmap.SP_BrowserReload),

                ActionDef.SEPARATOR,

                ActionDef(self.tr("&Remove Remote..."),
                          lambda: self.deleteRemote.emit(data),
                          QStyle.StandardPixmap.SP_TrashIcon),
            ]

        elif item == EItem.RemotesHeader:
            actions += [
                ActionDef(self.tr("&Add Remote..."),
                          self.newRemote),
            ]

        elif item == EItem.StashesHeader:
            actions += [
                ActionDef(self.tr("&New Stash..."),
                          self.newStash,
                          shortcuts=GlobalShortcuts.newStash),
            ]

        elif item == EItem.Stash:
            oid = pygit2.Oid(hex=data)

            actions += [
                ActionDef(self.tr("&Apply"),
                          lambda: self.applyStash.emit(oid)),

                ActionDef(self.tr("E&xport As Patch..."),
                          lambda: self.exportStashAsPatch.emit(oid)),

                ActionDef.SEPARATOR,

                ActionDef(self.tr("&Delete"),
                          lambda: self.dropStash.emit(oid),
                          QStyle.StandardPixmap.SP_TrashIcon),
            ]

        elif item == EItem.Submodule:
            actions += [
                ActionDef(self.tr("&Open submodule in {0}").format(qAppName()),
                          lambda: self.openSubmoduleRepo.emit(data)),

                ActionDef(self.tr("Open submodule &folder"),
                          lambda: self.openSubmoduleFolder.emit(data)),
            ]

        # --------------------

        ActionDef.addToQMenu(menu, actions)

        return menu

    def onCustomContextMenuRequested(self, localPoint: QPoint):
        globalPoint = self.mapToGlobal(localPoint)
        index: QModelIndex = self.indexAt(localPoint)
        if index.isValid():
            menu = self.generateMenuForEntry(*SidebarModel.unpackItemAndData(index), index=index)
            if menu.actions():
                menu.exec(globalPoint)
            menu.deleteLater()

    def refresh(self, repoState: RepoState):
        sidebarModel: SidebarModel = self.model()
        with Benchmark("Refresh sidebar cache"):
            sidebarModel.refreshCache(repoState.repo, repoState.hiddenBranches, repoState.refCache)
        self.expandAll()

    def onEntryClicked(self, item: EItem, data: str):
        if item == EItem.UncommittedChanges:
            self.uncommittedChangesClicked.emit()
        elif item == EItem.UnbornHead:
            pass
        elif item == EItem.DetachedHead:
            self.refClicked.emit("HEAD")
        elif item == EItem.LocalBranch:
            self.refClicked.emit(porcelain.HEADS_PREFIX + data)
        elif item == EItem.RemoteBranch:
            self.refClicked.emit(porcelain.REMOTES_PREFIX + data)
        elif item == EItem.Tag:
            self.refClicked.emit(porcelain.TAGS_PREFIX + data)
        elif item == EItem.Stash:
            self.commitClicked.emit(pygit2.Oid(hex=data))
        else:
            pass

    def onEntryDoubleClicked(self, item: EItem, data: str):
        if item == EItem.LocalBranch:
            self.switchToBranch.emit(data, True)  # ask for confirmation
        elif item == EItem.Remote:
            self.editRemote.emit(data)
        elif item == EItem.RemotesHeader:
            self.newRemote.emit()
        elif item == EItem.LocalBranchesHeader:
            self.newBranch.emit()
        elif item == EItem.UncommittedChanges:
            self.commitChanges.emit()
        elif item == EItem.Submodule:
            self.openSubmoduleRepo.emit(data)
        elif item == EItem.StashesHeader:
            self.newStash.emit()
        elif item == EItem.Stash:
            oid = pygit2.Oid(hex=data)
            self.applyStash.emit(oid)
        elif item == EItem.RemoteBranch:
            self.newTrackingBranch.emit(data)

    def currentChanged(self, current: QModelIndex, previous: QModelIndex):
        super().currentChanged(current, previous)
        if current.isValid():
            self.onEntryClicked(*SidebarModel.unpackItemAndData(current))

    def mouseDoubleClickEvent(self, event):
        # NOT calling "super().mouseDoubleClickEvent(event)" on purpose.
        index: QModelIndex = self.indexAt(event.pos())
        if event.button() == Qt.MouseButton.LeftButton and index.isValid():
            self.onEntryDoubleClicked(*SidebarModel.unpackItemAndData(index))

    def indicesForItemType(self, item: EItem) -> list[QModelIndex]:
        """ Unit testing helper """
        model: QAbstractItemModel = self.model()
        value = item.value
        indexList: list[QModelIndex] = model.match(model.index(0, 0), ROLE_EITEM, value, hits=-1, flags=Qt.MatchFlag.MatchRecursive)
        return indexList

    def datasForItemType(self, item: EItem, role: int = ROLE_USERDATA) -> list[str]:
        """ Unit testing helper """
        model: QAbstractItemModel = self.model()
        indices = self.indicesForItemType(item)
        return [model.data(index, role) for index in indices]

    def indexForRef(self, ref: str) -> QModelIndex | None:
        model: QAbstractItemModel = self.model()

        index = model.match(model.index(0, 0), ROLE_REF, ref, hits=1,
                            flags=Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchRecursive)

        if index:
            return index[0]
        else:
            return None

    def selectAnyRef(self, *refCandidates: str) -> QModelIndex | None:
        # Early out if any candidate ref is already selected
        with contextlib.suppress(IndexError):
            currentIndex = self.selectedIndexes()[0]
            if currentIndex and currentIndex.data(ROLE_REF) in refCandidates:
                return currentIndex

        # Find an index that matches any of the candidates
        for ref in refCandidates:
            index = self.indexForRef(ref)
            if index:
                self.setCurrentIndex(index)
                return index

        # There are no indices that match the candidates, so select nothing
        self.clearSelection()
        return None
