# -----------------------------------------------------------------------------
# Copyright (C) 2026 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

import re

from gitfourchette.qt import *
from gitfourchette.toolbox.textutils import stripHtml

# 0: Turn off debug rendering
# 1: Draw extents of blank label
# 2: Draw base menu text to verify that our overlaid text is aligned correctly
_DEBUGPAINT = 0


class QRichTextMenu(QMenu):
    """
    QMenu that can render actions with HTML text.
    """

    class RichTextAction(QAction):
        colorDoc: QTextDocument
        """Color text (not hovered)"""

        monoDoc: QTextDocument
        """Monochrome text (hovered)"""

        blankLabel: str
        """A string of spaces passed to QMenu's base paintEvent() so we can
        paint our HTML on top."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._leftOffset = -1

    def addRichTextAction(self, markup: str, accelerator: str = "") -> QAction:
        # Strip all HTML for fallback text used for accelerators
        plainText = stripHtml(markup)
        plainTextNoAccelerator = plainText

        # Inject <u> around the accelerator key in the markup (if hinted by style)
        # and inject '&' before the accelerator in plain text.
        if accelerator and (accelMatch := re.search(rf"(?![^<]*>){accelerator}", markup, re.IGNORECASE)):
            if self.style().styleHint(QStyle.StyleHint.SH_UnderlineShortcut):
                x, y = accelMatch.span()
                markup = markup[:x] + "<u>" + markup[x:y] + "</u>" + markup[y:]

            plainAccelMatch = re.search(accelerator, plainText, re.IGNORECASE)
            assert plainAccelMatch
            plainText = plainText[:plainAccelMatch.pos] + "&" + plainText[plainAccelMatch.pos:]

        # Derive monochrome markup for selected text.
        # Use highlight color, and kill any 'color' styling in inline CSS.
        monoColor = self.palette().color(QPalette.ColorGroup.Normal, QPalette.ColorRole.HighlightedText)
        monoMarkup = f"<html style='color: {monoColor.name()}'>"
        monoMarkup += re.sub(r"(style=['\"].*\b)(color:.+?)([;'\"])", r"\1\3", markup)

        action = QRichTextMenu.RichTextAction(self)

        action.colorDoc = QTextDocument(action)
        action.colorDoc.setHtml(markup)
        action.colorDoc.setDocumentMargin(0)

        action.monoDoc = QTextDocument(action)
        action.monoDoc.setHtml(monoMarkup)
        action.monoDoc.setDocumentMargin(0)

        fm = self.fontMetrics()
        spaceWidth = fm.horizontalAdvance(" " * 100) / 100
        plainWidth = fm.horizontalAdvance(plainTextNoAccelerator)
        idealWidth = action.colorDoc.idealWidth()

        # Prepare a blank label as wide as our HTML document. Breeze's
        # QMenu.paintEvent() will use this to adjust menu item widths.
        # (DON'T replace the action's actual text value so that accelerators
        # still work. Instead, the label is overridden in initStyleOption().)
        action.blankLabel = " " * round(idealWidth / spaceWidth)

        # Non-Breeze styles (including Breeze with custom QSS styling of QMenu)
        # compute menu item widths from action.text() instead. Pad it with
        # spaces just enough to fit our HTML document.
        plainText += " " * round((idealWidth - plainWidth) / spaceWidth)

        if _DEBUGPAINT:  # pragma: no cover
            action.blankLabel += "|b"
            plainText += "|p"

        action.setText(plainText)
        self.addAction(action)
        return action

    def initStyleOption(self, option: QStyleOptionMenuItem, action: QAction):
        super().initStyleOption(option, action)

        # Override text so super().paintEvent() draws a blank label
        if isinstance(action, QRichTextMenu.RichTextAction) and _DEBUGPAINT != 2:
            option.text = action.blankLabel

        # Cache left offset if needed (this needs a valid QStyleOptionMenuItem)
        if self._leftOffset < 0:
            self._leftOffset = self._computeLeftOffset(option)

    def _computeLeftOffset(self, option: QStyleOptionMenuItem):
        from gitfourchette.settings import prefs

        x = self.contentsMargins().left()
        x += self.style().pixelMetric(QStyle.PixelMetric.PM_MenuHMargin, option, self)

        if not option.menuHasCheckableItems:
            indicator = 0
        else:
            indicator = self.style().pixelMetric(QStyle.PixelMetric.PM_ExclusiveIndicatorWidth, option, self)

        offsets = {
            "fusion": 28,
            "breeze": 12 + indicator,
            "windows": 16,
            "macos": 18,
            "oxygen": 8 + indicator,
            "": 6 + indicator,  # built-in theme
        }

        x += offsets.get(prefs.qtStyle.lower(), offsets[""])
        return x

    def paintEvent(self, event: QPaintEvent):
        # First, let vanilla QMenu paint itself normally. It calls initStyleOption
        # for each item (that's where we clear the text for our own actions)
        super().paintEvent(event)

        # Then, paint our own HTML text over it
        painter = QPainter(self)
        fm = self.fontMetrics()

        for action in self.actions():
            if not isinstance(action, QRichTextMenu.RichTextAction):
                continue

            doc = action.monoDoc if action is self.activeAction() else action.colorDoc

            rect = self.actionGeometry(action)
            assert rect.isValid(), "action geometry invalid"
            x = rect.left() + self._leftOffset
            y = rect.top() + (rect.height() - fm.height()) / 2

            painter.save()
            painter.setClipRect(rect)
            painter.translate(QPoint(x, int(y)))
            doc.drawContents(painter)
            painter.restore()
