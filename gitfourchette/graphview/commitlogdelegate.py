import math

from gitfourchette import settings
from gitfourchette.forms.searchbar import SearchBar
from gitfourchette.graphview.commitlogmodel import CommitLogModel, SpecialRow
from gitfourchette.graphview.graphpaint import paintGraphFrame
from gitfourchette.porcelain import *
from gitfourchette.qt import *
from gitfourchette.repostate import RepoState, UC_FAKEID
from gitfourchette.toolbox import *
from dataclasses import dataclass
from contextlib import suppress
import traceback


@dataclass
class RefBox:
    icon: str
    color: QColor
    keepPrefix: bool = False


REFBOXES = {
    "refs/remotes/": RefBox("git-remote", QColor(Qt.GlobalColor.darkCyan)),
    "refs/tags/": RefBox("git-tag", QColor(Qt.GlobalColor.darkYellow)),
    "refs/heads/": RefBox("git-branch", QColor(Qt.GlobalColor.darkMagenta)),
    "stash@{": RefBox("git-stash", QColor(Qt.GlobalColor.darkGreen), keepPrefix=True),

    # detached HEAD as returned by Repo.map_commits_to_refs
    "HEAD": RefBox("achtung", QColor(Qt.GlobalColor.darkRed), keepPrefix=True),
}


ELISION = " […]"
ELISION_LENGTH = len(ELISION)


MAX_AUTHOR_CHARS = {
    AuthorDisplayStyle.INITIALS: 7,
    AuthorDisplayStyle.FULL_NAME: 20,
}


XMARGIN = 4
XSPACING = 6

NARROW_WIDTH = (500, 750)


class CommitLogDelegate(QStyledItemDelegate):
    def __init__(self, repoWidget, parent=None):
        super().__init__(parent)

        self.repoWidget = repoWidget

        self.mustRefreshMetrics = True
        self.hashCharWidth = 0
        self.dateMaxWidth = 0
        self.activeCommitFont = QFont()
        self.uncommittedFont = QFont()
        self.refboxFont = QFont()
        self.refboxFontMetrics = QFontMetricsF(self.refboxFont)
        self.homeRefboxFont = QFont()
        self.homeRefboxFontMetrics = QFontMetricsF(self.homeRefboxFont)

    def invalidateMetrics(self):
        self.mustRefreshMetrics = True

    def refreshMetrics(self, option: QStyleOptionViewItem):
        if not self.mustRefreshMetrics:
            return

        self.mustRefreshMetrics = False

        self.hashCharWidth = max(option.fontMetrics.horizontalAdvance(c) for c in "0123456789abcdef")

        self.activeCommitFont = QFont(option.font)
        self.activeCommitFont.setBold(True)

        self.uncommittedFont = QFont(option.font)
        self.uncommittedFont.setItalic(True)

        self.refboxFont = QFont(option.font)
        self.refboxFont.setWeight(QFont.Weight.Light)
        self.refboxFontMetrics = QFontMetricsF(self.refboxFont)

        self.homeRefboxFont = QFont(self.refboxFont)
        self.homeRefboxFont.setWeight(QFont.Weight.Bold)
        self.homeRefboxFontMetrics = QFontMetricsF(self.homeRefboxFont)

        wideDate = QDateTime.fromString("2999-12-25T23:59:59.999", Qt.DateFormat.ISODate)
        dateText = option.locale.toString(wideDate, settings.prefs.shortTimeFormat)
        if settings.prefs.authorDiffAsterisk:
            dateText += "*"
        self.dateMaxWidth = QFontMetrics(self.activeCommitFont).horizontalAdvance(dateText + " ")
        self.dateMaxWidth = int(self.dateMaxWidth)  # make sure it's an int for pyqt5 compat

    @property
    def state(self) -> RepoState:
        return self.repoWidget.state

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        try:
            self._paint(painter, option, index)
        except Exception as exc:  # pragma: no cover
            self._paintError(painter, option, index, exc)

    def _paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        hasFocus = option.state & QStyle.StateFlag.State_HasFocus
        isSelected = option.state & QStyle.StateFlag.State_Selected
        style = option.widget.style()
        palette: QPalette = option.palette
        outlineColor = palette.color(QPalette.ColorRole.Base)
        colorGroup = QPalette.ColorGroup.Normal if hasFocus else QPalette.ColorGroup.Inactive

        painter.save()

        # Draw default background
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, option, painter, option.widget)

        if isSelected:
            painter.setPen(palette.color(colorGroup, QPalette.ColorRole.HighlightedText))

        # Get metrics of '0' before setting a custom font,
        # so that alignments are consistent in all commits regardless of bold or italic.
        self.refreshMetrics(option)
        hcw = self.hashCharWidth

        # Set up rect
        rect = QRect(option.rect)
        rect.setLeft(rect.left() + XMARGIN)
        rect.setRight(rect.right() - XMARGIN)

        # Compute column bounds
        authorWidth = hcw * MAX_AUTHOR_CHARS.get(settings.prefs.authorDisplayStyle, 16)
        dateWidth = self.dateMaxWidth
        if rect.width() < NARROW_WIDTH[0]:
            authorWidth = 0
            dateWidth = 0
        elif rect.width() <= NARROW_WIDTH[1]:
            authorWidth = int(lerp(authorWidth/2, authorWidth, NARROW_WIDTH[0], NARROW_WIDTH[1], rect.width()))
        leftBoundHash = rect.left()
        leftBoundSummary = leftBoundHash + hcw * settings.prefs.shortHashChars + XSPACING
        leftBoundDate = rect.width() - dateWidth
        leftBoundName = leftBoundDate - authorWidth
        rightBound = rect.right()

        # Get the info we need about the commit
        commit: Commit | None = index.data(CommitLogModel.CommitRole)
        if commit:
            oid = commit.oid
            author = commit.author
            committer = commit.committer

            # TODO: If is stash, getCoreStashMessage
            summaryText, contd = messageSummary(commit.message, ELISION)
            hashText = commit.oid.hex[:settings.prefs.shortHashChars]
            authorText = abbreviatePerson(author, settings.prefs.authorDisplayStyle)

            qdt = QDateTime.fromSecsSinceEpoch(author.time)
            dateText = option.locale.toString(qdt, settings.prefs.shortTimeFormat)

            if settings.prefs.authorDiffAsterisk:
                if author.email != committer.email:
                    authorText += "*"
                if author.time != committer.time:
                    dateText += "*"

            if self.state.activeCommitOid == commit.oid:
                painter.setFont(self.activeCommitFont)

            searchBar: SearchBar = self.parent().searchBar
            searchTerm: str = searchBar.searchTerm
            searchTermLooksLikeHash: bool = searchBar.searchTermLooksLikeHash

            if not searchBar.isVisible():
                searchTerm = ""
        else:
            commit = None
            oid = None
            hashText = "·" * settings.prefs.shortHashChars
            authorText = ""
            dateText = ""
            searchTerm = ""
            searchTermLooksLikeHash = False
            painter.setFont(self.uncommittedFont)

            specialRowKind: SpecialRow = index.data(CommitLogModel.SpecialRowRole)

            if specialRowKind == SpecialRow.UncommittedChanges:
                oid = UC_FAKEID
                summaryText = self.tr("Uncommitted changes")
                # Append draft message if any
                draftMessage = self.state.getDraftCommitMessage()
                if draftMessage:
                    draftMessage = messageSummary(draftMessage)[0].strip()
                    draftIntro = self.tr("Commit draft:")
                    summaryText += f" – {draftIntro} {tquo(draftMessage)}"
                # Prefix with change count if available
                numChanges = self.state.numUncommittedChanges
                if numChanges > 0:
                    summaryText = f"({numChanges}) {summaryText}"

            elif specialRowKind == SpecialRow.TruncatedHistory:
                if self.state.uiPrefs.hiddenRefPatterns or self.state.uiPrefs.hiddenStashCommits:
                    summaryText = self.tr("History truncated to {0} commits (including hidden branches)")
                else:
                    summaryText = self.tr("History truncated to {0} commits")
                summaryText = summaryText.format(option.widget.locale().toString(self.state.numRealCommits))

            elif specialRowKind == SpecialRow.EndOfShallowHistory:
                summaryText = self.tr("Shallow clone – End of commit history")

            else:
                summaryText = f"*** Unsupported special row {specialRowKind}"

        # Get metrics now so the message gets elided according to the custom font style
        # that may have been just set for this commit.
        metrics: QFontMetrics = painter.fontMetrics()

        def elide(text):
            return metrics.elidedText(text, Qt.TextElideMode.ElideRight, rect.width())

        def highlight(fullText: str, needlePos: int, needleLen: int):
            SearchBar.highlightNeedle(painter, rect, fullText, needlePos, needleLen)

        # ------ Hash
        charRect = QRect(leftBoundHash, rect.top(), hcw, rect.height())
        painter.save()
        if not isSelected:  # use muted color for hash if not selected
            painter.setPen(palette.color(colorGroup, QPalette.ColorRole.PlaceholderText))
        for hashChar in hashText:
            painter.drawText(charRect, Qt.AlignmentFlag.AlignCenter, hashChar)
            charRect.translate(hcw, 0)
        painter.restore()

        # ------ Highlight searched hash
        if searchTerm and searchTermLooksLikeHash and commit and commit.hex.startswith(searchTerm):
            x1 = 0
            x2 = min(len(hashText), len(searchTerm)) * hcw
            SearchBar.highlightNeedle(painter, rect, hashText, 0, len(searchTerm), x1, x2)

        # ------ Graph
        rect.setLeft(leftBoundSummary)
        if oid is not None:
            paintGraphFrame(self.state, oid, painter, rect, outlineColor)
            rect.setLeft(rect.right())

        # ------ Refboxes
        if oid in self.state.reverseRefCache:
            homeBranch = RefPrefix.HEADS + self.state.homeBranch
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            for refName in self.state.reverseRefCache[oid]:
                self._paintRefbox(painter, rect, refName, refName == homeBranch)
            painter.restore()

        # ------ Icons
        if oid == UC_FAKEID:
            r = QRect(rect)
            r.setWidth(min(16, r.height()))
            remap = "" if not isSelected else f"gray={painter.pen().color().name()}"
            icon = stockIcon("git-workdir", remap)
            icon.paint(painter, r, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            rect.setLeft(r.right() + 4)

        # ------ Message
        # use muted color for foreign commit messages if not selected
        if not isSelected and commit and commit.oid in self.state.foreignCommits:
            painter.setPen(Qt.GlobalColor.gray)
        if oid is not None and oid != UC_FAKEID:
            rect.setRight(leftBoundName - XMARGIN)
        else:
            rect.setRight(rightBound)

        elidedSummaryText = elide(summaryText)
        painter.drawText(rect, Qt.AlignmentFlag.AlignVCenter, elidedSummaryText)

        # ------ Highlight search term
        if searchTerm and commit and searchTerm in commit.message.lower():
            needlePos = summaryText.lower().find(searchTerm)
            if needlePos < 0:
                needlePos = len(summaryText) - ELISION_LENGTH
                needleLen = ELISION_LENGTH
            else:
                needleLen = len(searchTerm)
            highlight(summaryText, needlePos, needleLen)

        # ------ Author
        rect.setLeft(leftBoundName)
        rect.setRight(leftBoundDate - XMARGIN)
        painter.drawText(rect, Qt.AlignmentFlag.AlignVCenter, elide(authorText) + "  ")

        # ------ Highlight searched author
        if searchTerm and commit:
            needlePos = authorText.lower().find(searchTerm)
            if needlePos >= 0:
                highlight(authorText, needlePos, len(searchTerm))

        # ------ Date
        rect.setLeft(leftBoundDate)
        rect.setRight(rightBound)
        painter.drawText(rect, Qt.AlignmentFlag.AlignVCenter, elide(dateText))

        # ----------------
        painter.restore()

        # Tooltip metrics
        summaryIsElided = len(elidedSummaryText) == 0 or elidedSummaryText.endswith(("…", ELISION))
        model = index.model()
        model.setData(index, summaryIsElided, CommitLogModel.MessageElidedRole)
        model.setData(index, leftBoundName if authorWidth != 0 else -1, CommitLogModel.AuthorColumnXRole)

    def _paintRefbox(self, painter: QPainter, rect: QRect, refName: str, isHome: bool):
        if refName == 'HEAD' and not self.state.headIsDetached:
            return

        prefix = next(prefix for prefix in REFBOXES if refName.startswith(prefix))
        refboxDef = REFBOXES[prefix]
        if not refboxDef.keepPrefix:
            text = refName.removeprefix(prefix)
        else:
            text = refName
        color = refboxDef.color
        icon = refboxDef.icon
        if refName == 'HEAD' and self.state.headIsDetached:
            text = self.tr("detached HEAD")

        if isHome:
            font = self.homeRefboxFont
            fontMetrics = self.homeRefboxFontMetrics
            icon = "git-home"
        else:
            font = self.refboxFont
            fontMetrics = self.refboxFontMetrics

        painter.setFont(font)
        painter.setPen(color)

        hPadding = 2
        vMargin = max(0, math.ceil((rect.height() - 16) / 4))

        if icon:
            iconRect = QRect(rect)
            iconRect.adjust(2, vMargin, 0, -2)
            iconSize = min(16, iconRect.height())
            iconRect.setWidth(iconSize)
        else:
            iconSize = 0

        boxRect = QRect(rect)
        text = fontMetrics.elidedText(text, Qt.TextElideMode.ElideRight, 100)
        textWidth = int(fontMetrics.horizontalAdvance(text))  # must be int for pyqt5 compat!
        boxRect.setWidth(2 + iconSize + 1 + textWidth + hPadding)

        frameRect = QRectF(boxRect)
        frameRect.adjust(.5, vMargin + .5, .5, -(vMargin + .5))
        painter.drawRoundedRect(frameRect, 4, 4)

        if icon:
            icon = stockIcon(icon, f"gray={color.name()}")
            icon.paint(painter, iconRect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        textRect = QRect(boxRect)
        textRect.adjust(0, 0, -hPadding, 0)
        painter.drawText(textRect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, text)

        # Advance caller rectangle
        rect.setLeft(boxRect.right() + 6)

    def _paintError(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex, exc: BaseException):  # pragma: no cover
        """Last-resort row drawing routine used if _paint raises an exception."""

        text = "?" * 7
        with suppress(BaseException):
            commit: Commit = index.data(CommitLogModel.CommitRole)
            text = commit.oid.hex[:7]
        with suppress(BaseException):
            details = traceback.format_exception(exc.__class__, exc, exc.__traceback__)
            text += " " + shortenTracebackPath(details[-2].splitlines(False)[0]) + ":: " + repr(exc)

        if option.state & QStyle.StateFlag.State_Selected:
            bg, fg = Qt.GlobalColor.red, Qt.GlobalColor.white
        else:
            bg, fg = option.palette.color(QPalette.ColorRole.Base), Qt.GlobalColor.red

        painter.restore()
        painter.save()
        painter.fillRect(option.rect, bg)
        painter.setPen(fg)
        painter.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.SmallestReadableFont))
        painter.drawText(option.rect, Qt.AlignmentFlag.AlignVCenter, text)
        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        mult = settings.prefs.graphRowHeight
        r = super().sizeHint(option, index)
        r.setHeight(option.fontMetrics.height() * mult // 100)
        return r
