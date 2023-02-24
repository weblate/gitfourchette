from gitfourchette import porcelain
from gitfourchette.globalshortcuts import GlobalShortcuts
from gitfourchette.qt import *
from gitfourchette.repostate import RepoState
from gitfourchette.util import escamp, stockIcon
from html import escape
from typing import Any
import enum
import pygit2

ROLE_USERDATA = Qt.ItemDataRole.UserRole + 0
ROLE_EITEM = Qt.ItemDataRole.UserRole + 1
ROLE_ISHIDDEN = Qt.ItemDataRole.UserRole + 2

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

    def refreshCache(self, repo: pygit2.Repository, hiddenBranches: list[str]):
        self.beginResetModel()

        self.repo = repo

        self._localBranches = [b for b in repo.branches.local]

        self._tracking = []
        for branchName in self._localBranches:
            upstream = self.repo.branches.local[branchName].upstream
            if not upstream:
                self._tracking.append("")
            else:
                self._tracking.append(upstream.shorthand)

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

        self._stashes = repo.listall_stashes()

        self._remotes = [r.name for r in repo.remotes]
        self._remoteURLs = [repo.remotes[r].url for r in self._remotes]
        self._remoteBranchesDict = porcelain.getRemoteBranchNames(repo)

        self._tags = sorted(porcelain.getTagNames(repo))

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
        userRole = role == ROLE_USERDATA
        toolTipRole = role == Qt.ItemDataRole.ToolTipRole
        sizeHintRole = role == Qt.ItemDataRole.SizeHintRole
        hiddenRole = role == ROLE_ISHIDDEN
        fontRole = role == Qt.ItemDataRole.FontRole

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
            elif toolTipRole:
                text = self.tr("Local branch “{0}”").format(branchName)
                if branchName == self._checkedOut:
                    text += "\n" + ACTIVE_BULLET + self.tr("Active branch")
                if self._tracking[branchNo]:
                    text += "\n" + self.tr("Tracking remote branch “{0}”").format(self._tracking[branchNo])
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
                return ACTIVE_BULLET + self.tr("[detached head]")
            elif userRole:
                return self._detachedHead
            elif toolTipRole:
                return self.tr("Detached HEAD") + " @ " + self._detachedHead
            elif hiddenRole:
                return False

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
            elif hiddenRole:
                return False

        elif item == EItem.Stash:
            stash = self._stashes[row]
            if displayRole:
                return porcelain.getCoreStashMessage(stash.message)
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
    commit = Signal()

    newBranch = Signal()
    newBranchFromLocalBranch = Signal(str)
    renameBranch = Signal(str)
    deleteBranch = Signal(str)
    switchToBranch = Signal(str)
    mergeBranchIntoActive = Signal(str)
    rebaseActiveOntoBranch = Signal(str)
    pushBranch = Signal(str)
    pullBranch = Signal(str)
    toggleHideBranch = Signal(str)
    newTrackingBranch = Signal(str)
    fetchRemoteBranch = Signal(str)
    renameRemoteBranch = Signal(str)
    deleteRemoteBranch = Signal(str)
    editTrackingBranch = Signal(str)

    newRemote = Signal()
    fetchRemote = Signal(str)
    editRemote = Signal(str)
    deleteRemote = Signal(str)

    newStash = Signal()
    popStash = Signal(pygit2.Oid)
    applyStash = Signal(pygit2.Oid, bool)  # bool: ask for confirmation before applying
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

    def updateHiddenBranches(self, hiddenBranches: list[str]):
        self.model().updateHiddenBranches(hiddenBranches)

    def generateMenuForEntry(self, item: EItem, data: str = "", menu: QMenu = None, index: QModelIndex = None):
        if menu is None:
            menu = QMenu(self)
            menu.setObjectName("SidebarContextMenu")

        if item == EItem.LocalBranchesHeader:
            newBranchAction = menu.addAction(self.tr("&New Branch..."), lambda: self.newBranch.emit())
            newBranchAction.setShortcuts(GlobalShortcuts.newBranch)

        elif item == EItem.LocalBranch:
            model: SidebarModel = self.model()
            repo = model.repo
            branch = repo.branches.local[data]

            activeBranchName = porcelain.getActiveBranchShorthand(repo)
            isCurrentBranch = branch and branch.is_checked_out()

            switchAction: QAction = menu.addAction(self.tr("&Switch to “{0}”").format(escamp(data)))
            menu.addSeparator()
            mergeAction: QAction = menu.addAction(self.tr("&Merge “{0}” into “{1}”...").format(escamp(data), escamp(activeBranchName)))
            rebaseAction: QAction = menu.addAction(self.tr("&Rebase “{0}” onto “{1}”...").format(escamp(activeBranchName), escamp(data)))

            switchAction.setIcon(QIcon.fromTheme("document-swap"))

            for action in switchAction, mergeAction, rebaseAction:
                action.setEnabled(False)

            menu.addSeparator()
            pushBranchAction = menu.addAction(stockIcon("vcs-push"), self.tr("&Push..."), lambda: self.pushBranch.emit(data))
            fetchBranchAction = menu.addAction(self.tr("&Fetch..."), lambda: self.fetchRemoteBranch.emit(branch.upstream.shorthand))
            pullBranchAction = menu.addAction(stockIcon("vcs-pull"), self.tr("Pul&l..."), lambda: self.pullBranch.emit(data))
            menu.addAction(self.tr("Set &Tracked Branch..."), lambda: self.editTrackingBranch.emit(data))

            hasUpstream = bool(branch.upstream)
            pullBranchAction.setEnabled(hasUpstream)
            fetchBranchAction.setEnabled(hasUpstream)

            menu.addSeparator()
            menu.addAction(self.tr("Re&name..."), lambda: self.renameBranch.emit(data))
            a = menu.addAction(self.tr("&Delete..."), lambda: self.deleteBranch.emit(data))
            a.setIcon(QIcon.fromTheme("vcs-branch-delete"))

            menu.addSeparator()
            menu.addAction(self.tr("New branch from here..."), lambda: self.newBranchFromLocalBranch.emit(data))

            menu.addSeparator()
            a = menu.addAction(self.tr("&Hide in graph"), lambda: self.toggleHideBranch.emit("refs/heads/" + data))
            a.setCheckable(True)
            if index:  # in test mode, we may not have an index
                isBranchHidden = self.model().data(index, ROLE_ISHIDDEN)
                a.setChecked(isBranchHidden)

            if not isCurrentBranch:
                switchAction.triggered.connect(lambda: self.switchToBranch.emit(data))
                switchAction.setEnabled(True)

                pushBranchAction.setShortcuts(GlobalShortcuts.pushBranch)
                pullBranchAction.setShortcuts(GlobalShortcuts.pullBranch)

                if activeBranchName:
                    mergeAction.triggered.connect(lambda: self.mergeBranchIntoActive.emit(data))
                    rebaseAction.triggered.connect(lambda: self.rebaseActiveOntoBranch.emit(data))

                    mergeAction.setEnabled(True)
                    rebaseAction.setEnabled(True)

        elif item == EItem.RemoteBranch:
            menu.addAction(self.tr("New local branch tracking {0}...").format(escamp(data)),
                           lambda: self.newTrackingBranch.emit(data))

            a = menu.addAction(self.tr("Fetch this remote branch..."), lambda: self.fetchRemoteBranch.emit(data))
            a.setIcon(stockIcon(QStyle.StandardPixmap.SP_BrowserReload))

            menu.addSeparator()

            a = menu.addAction(self.tr("Rename branch on remote..."), lambda: self.renameRemoteBranch.emit(data))

            a = menu.addAction(self.tr("Delete branch on remote..."), lambda: self.deleteRemoteBranch.emit(data))
            a.setIcon(stockIcon(QStyle.StandardPixmap.SP_TrashIcon))

            menu.addSeparator()
            a = menu.addAction(self.tr("&Hide in graph"), lambda: self.toggleHideBranch.emit("refs/remotes/" + data))
            a.setCheckable(True)
            if index:  # in test mode, we may not have an index
                isBranchHidden = self.model().data(index, ROLE_ISHIDDEN)
                a.setChecked(isBranchHidden)

        elif item == EItem.Remote:
            a = menu.addAction(self.tr("&Edit Remote..."), lambda: self.editRemote.emit(data))
            a.setIcon(QIcon.fromTheme("document-edit"))

            a = menu.addAction(self.tr("&Fetch all branches on this remote..."), lambda: self.fetchRemote.emit(data))
            a.setIcon(stockIcon(QStyle.StandardPixmap.SP_BrowserReload))

            menu.addSeparator()

            a = menu.addAction(self.tr("&Delete Remote"), lambda: self.deleteRemote.emit(data))
            a.setIcon(stockIcon(QStyle.StandardPixmap.SP_TrashIcon))

        elif item == EItem.RemotesHeader:
            menu.addAction(self.tr("&Add Remote..."), lambda: self.newRemote.emit())

        elif item == EItem.StashesHeader:
            newStashAction = menu.addAction(self.tr("&New Stash..."), lambda: self.newStash.emit())
            newStashAction.setShortcuts(GlobalShortcuts.newStash)

        elif item == EItem.Stash:
            oid = pygit2.Oid(hex=data)
            menu.addAction(self.tr("&Pop (apply and delete)"), lambda: self.popStash.emit(oid))
            menu.addAction(self.tr("&Apply"), lambda: self.applyStash.emit(oid, False))  # False: don't ask for confirmation
            menu.addSeparator()
            menu.addAction(stockIcon(QStyle.StandardPixmap.SP_TrashIcon), self.tr("&Delete"), lambda: self.dropStash.emit(oid))

        elif item == EItem.Submodule:
            menu.addAction(self.tr("&Open submodule in {0}").format(QApplication.applicationDisplayName()), lambda: self.openSubmoduleRepo.emit(data))
            menu.addAction(self.tr("Open submodule &folder"), lambda: self.openSubmoduleFolder.emit(data))

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
        sidebarModel.refreshCache(repoState.repo, repoState.hiddenBranches)
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
            self.switchToBranch.emit(data)
        elif item == EItem.Remote:
            self.editRemote.emit(data)
        elif item == EItem.RemotesHeader:
            self.newRemote.emit()
        elif item == EItem.LocalBranchesHeader:
            self.newBranch.emit()
        elif item == EItem.UncommittedChanges:
            self.commit.emit()
        elif item == EItem.Submodule:
            self.openSubmoduleRepo.emit(data)
        elif item == EItem.StashesHeader:
            self.newStash.emit()
        elif item == EItem.Stash:
            oid = pygit2.Oid(hex=data)
            self.applyStash.emit(oid, True)  # ask for confirmation

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
