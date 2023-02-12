from gitfourchette import colors
from gitfourchette import settings
from gitfourchette.graphpaint import paintGraphFrame
from gitfourchette.qt import *
from gitfourchette.repostate import RepoState
from gitfourchette.util import messageSummary
from dataclasses import dataclass
from datetime import datetime
import pygit2
import re


@dataclass
class RefCallout:
    color: QColor
    keepPrefix: bool = False


CALLOUTS = {
    "refs/remotes/": RefCallout(QColor(Qt.GlobalColor.darkCyan)),
    "refs/tags/": RefCallout(QColor(Qt.GlobalColor.darkYellow)),
    "refs/heads/": RefCallout(QColor(Qt.GlobalColor.darkMagenta)),
    "stash@{": RefCallout(QColor(Qt.GlobalColor.darkGreen), keepPrefix=True),
}


INITIALS_PATTERN = re.compile(r"(?:^|\s|-)+([^\s\-])[^\s\-]*")


def abbreviatePerson(sig: pygit2.Signature, style: settings.AuthorDisplayStyle = settings.AuthorDisplayStyle.FULL_NAME):
    if style == settings.AuthorDisplayStyle.FULL_NAME:
        return sig.name
    elif style == settings.AuthorDisplayStyle.FIRST_NAME:
        return sig.name.split(' ')[0]
    elif style == settings.AuthorDisplayStyle.LAST_NAME:
        return sig.name.split(' ')[-1]
    elif style == settings.AuthorDisplayStyle.INITIALS:
        return re.sub(INITIALS_PATTERN, r"\1", sig.name)
    elif style == settings.AuthorDisplayStyle.FULL_EMAIL:
        return sig.email
    elif style == settings.AuthorDisplayStyle.ABBREVIATED_EMAIL:
        emailParts = sig.email.split('@', 1)
        if len(emailParts) == 2 and emailParts[1] == "users.noreply.github.com":
            # Strip ID from GitHub noreply addresses (1234567+username@users.noreply.github.com)
            return emailParts[0].split('+', 1)[-1]
        else:
            return emailParts[0]
    else:
        return sig.email


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
        self.smallFont.setWeight(QFont.Weight.Light)
        self.smallFontMetrics = QFontMetricsF(self.smallFont)

    @property
    def state(self) -> RepoState:
        return self.repoWidget.state

    def paint(self, painter, option, index):
        hasFocus = option.state & QStyle.StateFlag.State_HasFocus
        isSelected = option.state & QStyle.StateFlag.State_Selected

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
        ColW_Hash = settings.prefs.shortHashChars + 1
        ColW_Date = 20
        if settings.prefs.authorDisplayStyle == settings.AuthorDisplayStyle.INITIALS:
            ColW_Author = 8
        elif settings.prefs.authorDisplayStyle == settings.AuthorDisplayStyle.FULL_NAME:
            ColW_Author = 20
        else:
            ColW_Author = 16

        painter.save()

        palette: QPalette = option.palette
        colorGroup = QPalette.ColorGroup.Normal if hasFocus else QPalette.ColorGroup.Inactive

        if isSelected:
            #if option.state & QStyle.StateFlag.State_HasFocus:
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
            commit: pygit2.Commit = index.data()
            # TODO: If is stash, getCoreStashMessage
            summaryText, contd = messageSummary(commit.message)
            hashText = commit.oid.hex[:settings.prefs.shortHashChars]
            authorText = abbreviatePerson(commit.author, settings.prefs.authorDisplayStyle)
            dateText = datetime.fromtimestamp(commit.author.time).strftime(settings.prefs.shortTimeFormat)
            if self.state.activeCommitOid == commit.oid:
                painter.setFont(self.activeCommitFont)
        else:
            commit = None
            summaryText = self.tr("[Uncommitted Changes]")
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
        if not isSelected:  # use muted color for hash if not selected
            painter.setPen(palette.color(colorGroup, QPalette.ColorRole.PlaceholderText))
        for hashChar in hashText:
            painter.drawText(charRect, Qt.AlignmentFlag.AlignCenter, hashChar)
            charRect.translate(self.hashCharWidth, 0)
        painter.restore()

        # ------ Graph
        rect.setLeft(rect.right())
        if commit is not None:
            paintGraphFrame(self.state, commit, painter, rect, outlineColor)

        # ------ Callouts
        if commit is not None and commit.oid in self.state.commitsToRefs:
            for refName in self.state.commitsToRefs[commit.oid]:
                calloutText = refName
                calloutColor = Qt.GlobalColor.darkMagenta

                for prefix in CALLOUTS:
                    if refName.startswith(prefix):
                        calloutDef = CALLOUTS[prefix]
                        if not calloutDef.keepPrefix:
                            calloutText = refName.removeprefix(prefix)
                        calloutColor = calloutDef.color
                        break

                painter.save()
                painter.setFont(self.smallFont)
                painter.setPen(calloutColor)
                rect.setLeft(rect.right())
                label = F"[{calloutText}] "
                rect.setWidth(int(self.smallFontMetrics.horizontalAdvance(label)))  # must be int for pyqt5 compat!
                painter.drawText(rect, Qt.AlignmentFlag.AlignVCenter, label)
                painter.restore()

        def elide(text):
            return metrics.elidedText(text, Qt.TextElideMode.ElideRight, rect.width())

        # ------ message
        # use muted color for foreign commit messages if not selected
        if not isSelected and commit and commit.oid in self.state.foreignCommits:
             painter.setPen(Qt.GlobalColor.gray)
        rect.setLeft(rect.right())
        rect.setRight(option.rect.right() - (ColW_Author + ColW_Date) * self.hashCharWidth - XMargin)
        painter.drawText(rect, Qt.AlignmentFlag.AlignVCenter, elide(summaryText))

        # ------ Author
        rect.setLeft(rect.right())
        rect.setWidth(ColW_Author * self.hashCharWidth)
        painter.drawText(rect, Qt.AlignmentFlag.AlignVCenter, elide(authorText))

        # ------ Date
        rect.setLeft(rect.right())
        rect.setWidth(ColW_Date * self.hashCharWidth)
        painter.drawText(rect, Qt.AlignmentFlag.AlignVCenter, elide(dateText))

        # ----------------
        painter.restore()
        pass  # QStyledItemDelegate.paint(self, painter, option, index)

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        r = super().sizeHint(option, index)
        r.setHeight(option.fontMetrics.height())
        return r
