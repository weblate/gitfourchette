from allgit import *
from allqt import *
from datetime import datetime
from graphpaint import paintGraphFrame
from repostate import RepoState
from util import messageSummary
import colors
import settings


REF_PREFIXES = {
    "refs/remotes/": Qt.darkCyan,
    "refs/tags/": Qt.darkYellow,
    "refs/heads/": Qt.darkMagenta,
}


class GraphDelegate(QStyledItemDelegate):
    def __init__(self, repoWidget, parent=None):
        super().__init__(parent)
        self.repoWidget = repoWidget
        self.hashCharWidth = 0

        self.activeCommitFont = QFont()
        self.activeCommitFont.setBold(True)

        self.uncommittedFont = QFont()
        self.uncommittedFont.setItalic(True)

        self.smallFont = QFont()
        self.smallFont.setWeight(QFont.Light)
        self.smallFontMetrics = QFontMetrics(self.smallFont)

    @property
    def state(self) -> RepoState:
        return self.repoWidget.state

    def paint(self, painter, option, index):
        hasFocus = option.state & QStyle.State_HasFocus
        isSelected = option.state & QStyle.State_Selected

        # Draw selection background _underneath_ the style's default graphics.
        # This is a workaround for the "windowsvista" style, which does not draw a solid color background for
        # selected items -- instead, it draws a very slight alpha overlay on _top_ of the item.
        # The problem is that its palette still returns white for foreground text, so the result would be unreadable
        # if we didn't draw a strong solid-color background. Most other styles draw their own background as a solid
        # color, so this rect is probably not visible outside of "windowsvista".
        if hasFocus and isSelected:
            painter.fillRect(option.rect, option.palette.color(QPalette.ColorRole.Highlight))

        outlineColor = option.palette.color(QPalette.ColorRole.Base)

        super().paint(painter, option, index)

        XMargin = 4
        ColW_Author = 16
        ColW_Hash = settings.prefs.shortHashChars + 1
        ColW_Date = 20

        painter.save()

        palette: QPalette = option.palette
        colorGroup = QPalette.ColorGroup.Normal if hasFocus else QPalette.ColorGroup.Inactive

        if isSelected:
            #if option.state & QStyle.State_HasFocus:
            #    painter.fillRect(option.rect, palette.color(pcg, QPalette.ColorRole.Highlight))
            painter.setPen(palette.color(colorGroup, QPalette.ColorRole.HighlightedText))

        rect = QRect(option.rect)
        rect.setLeft(rect.left() + XMargin)
        rect.setRight(rect.right() - XMargin)

        # Get metrics of '0' before setting a custom font,
        # so that alignments are consistent in all commits regardless of bold or italic.
        if self.hashCharWidth == 0:
            self.hashCharWidth = max(painter.fontMetrics().horizontalAdvance(c) for c in "0123456789abcdef")

        if index.row() > 0:
            commit: Commit = index.data()
            summaryText, contd = messageSummary(commit.message)
            hashText = commit.oid.hex[:settings.prefs.shortHashChars]
            authorText = commit.author.email.split('@')[0]
            dateText = datetime.fromtimestamp(commit.author.time).strftime(settings.prefs.shortTimeFormat)
            if self.state.activeCommitOid == commit.oid:
                painter.setFont(self.activeCommitFont)
        else:
            commit: Commit = None
            summaryText = "[Uncommitted Changes]"
            hashText = "·" * settings.prefs.shortHashChars
            authorText = ""
            dateText = ""
            painter.setFont(self.uncommittedFont)

            draftCommitMessage = self.state.getDraftCommitMessage()
            if draftCommitMessage:
                summaryText += F" {messageSummary(draftCommitMessage)[0]}"

        # Get metrics now so the message gets elided according to the custom font style
        # that may have been just set for this commit.
        metrics = painter.fontMetrics()

        # ------ Hash
        rect.setWidth(ColW_Hash * self.hashCharWidth)
        charRect = QRect(rect.left(), rect.top(), self.hashCharWidth, rect.height())
        painter.save()
        painter.setPen(palette.color(colorGroup, QPalette.ColorRole.PlaceholderText))
        for hashChar in hashText:
            painter.drawText(charRect, Qt.AlignCenter, hashChar)
            charRect.translate(self.hashCharWidth, 0)
        painter.restore()

        # ------ Graph
        rect.setLeft(rect.right())
        if commit is not None:
            paintGraphFrame(self.state, commit, painter, rect, outlineColor)

        # ------ Refs
        if commit is not None and commit.oid in self.state.refsByCommit:
            for refName in self.state.refsByCommit[commit.oid]:
                shortRefName = refName
                refColor = Qt.darkMagenta
                for prefix in REF_PREFIXES:
                    if refName.startswith(prefix):
                        shortRefName = refName[len(prefix):]
                        refColor = REF_PREFIXES[prefix]
                        break
                painter.save()
                painter.setFont(self.smallFont)
                painter.setPen(refColor)
                rect.setLeft(rect.right())
                label = F"[{shortRefName}] "
                rect.setWidth(self.smallFontMetrics.horizontalAdvance(label) + 1)
                painter.drawText(rect, Qt.AlignVCenter, label)
                painter.restore()

        def elide(text):
            return metrics.elidedText(text, Qt.ElideRight, rect.width())

        # ------ message
        ''' TODO: pygit2 migration
        if commit and not meta.hasLocal:
             painter.setPen(QColor(Qt.gray))
        '''
        rect.setLeft(rect.right())
        rect.setRight(option.rect.right() - (ColW_Author + ColW_Date) * self.hashCharWidth - XMargin)
        painter.drawText(rect, Qt.AlignVCenter, elide(summaryText))

        # ------ Author
        rect.setLeft(rect.right())
        rect.setWidth(ColW_Author * self.hashCharWidth)
        painter.drawText(rect, Qt.AlignVCenter, elide(authorText))

        # ------ Date
        rect.setLeft(rect.right())
        rect.setWidth(ColW_Date * self.hashCharWidth)
        painter.drawText(rect, Qt.AlignVCenter, elide(dateText))

        # ------ Debug (show redrawn rows from last refresh)
        ''' TODO: pygit2 migration
        if settings.prefs.debug_showDirtyCommitsAfterRefresh and commit and meta.debugPrefix:
            rect = QRect(option.rect)
            rect.setLeft(rect.left() + XMargin + (ColW_Hash-3) * self.hashCharWidth)
            rect.setRight(rect.left() + 3*self.hashCharWidth)
            painter.fillRect(rect, colors.rainbow[meta.batchID % len(colors.rainbow)])
            painter.drawText(rect, Qt.AlignVCenter, "-"+meta.debugPrefix)
        '''

        # ----------------
        painter.restore()
        pass  # QStyledItemDelegate.paint(self, painter, option, index)

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        r = super().sizeHint(option, index)
        r.setHeight(option.fontMetrics.height())
        return r
