# -----------------------------------------------------------------------------
# Copyright (C) 2026 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

import re

from gitfourchette import settings
from gitfourchette.qt import *
from gitfourchette.toolbox import stripHtml

# The QTextBlockFormat.LineHeightTypes enum is weird in both PySide6 and PyQt6
_LineHeightTypes_FixedHeight = int(
    QTextBlockFormat.LineHeightTypes.FixedHeight if QT5
    else QTextBlockFormat.LineHeightTypes.FixedHeight.value)  # type: ignore[call-overload]


class RebaseMenuStyle(QProxyStyle):
    def __init__(self):
        # Don't pass application-wide QStyle to the constructor, otherwise
        # QProxyStyle will take ownership of it!
        style = settings.prefs.qtStyle
        super().__init__(style)

        self.colorDocuments = {}
        self.monochromeDocuments = {}

    def prepareRichLabel(self, markup: str, accelerator: str = ""):
        plainText = stripHtml(markup)

        if accelerator:
            try:
                u = plainText.lower().index(accelerator.lower())
                plainText = plainText[:u] + "&" + plainText[u:]
            except LookupError:
                accelerator = ""

        colorDoc = QTextDocument(self)
        colorDoc.setHtml(markup)

        monochromeMarkup = re.sub(r"\bcolor:.+?[;'\"]", "", markup)
        monochromeDoc = QTextDocument(self)
        monochromeDoc.setHtml(monochromeMarkup)

        if accelerator:
            for doc in colorDoc, monochromeDoc:
                cursor = doc.find(accelerator)
                if not cursor.isNull():
                    fmt = QTextCharFormat()
                    fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SingleUnderline)
                    cursor.mergeCharFormat(fmt)

        # Hack: some wiggle room to account for bold
        plainText += " " * (len(plainText) // 8)

        self.colorDocuments[plainText] = colorDoc
        self.monochromeDocuments[plainText] = monochromeDoc

        return plainText

    def drawControl(self, element: QStyle.ControlElement, option: QStyleOption, painter: QPainter, widget: QWidget | None = None):
        if (
                element != QStyle.ControlElement.CE_MenuItem
                or not isinstance(option, QStyleOptionMenuItem)  # pragma: no cover - PyQt6 can be weird here, ignore
        ):
            super().drawControl(element, option, painter, widget)
            return

        plainText = option.text
        option.text = ""

        # Native background/selection (no text!)
        super().drawControl(element, option, painter, widget)

        textRect = QRect(option.rect)
        if option.menuHasCheckableItems:
            textRect.adjust(28, 0, 0, 0)

        isSelected = bool(option.state & QStyle.StateFlag.State_Selected)
        doc = (self.monochromeDocuments if isSelected else self.colorDocuments)[plainText]

        # Adjust width
        doc.setTextWidth(textRect.width())

        # Adjust line height
        capHeight = painter.fontMetrics().capHeight()
        fmt = QTextBlockFormat()
        fmt.setLineHeight(int(capHeight + (textRect.height() - capHeight) / 2), _LineHeightTypes_FixedHeight)
        QTextCursor(doc).mergeBlockFormat(fmt)

        painter.save()
        painter.setClipRect(textRect)
        painter.translate(textRect.left(), textRect.top())
        doc.drawContents(painter)
        painter.restore()
