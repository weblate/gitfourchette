# -----------------------------------------------------------------------------
# Copyright (C) 2026 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

from gitfourchette import settings
from gitfourchette.qt import *
from gitfourchette.toolbox import stripHtml


class RebaseMenuStyle(QProxyStyle):
    def __init__(self):
        # Don't pass application-wide QStyle to the constructor, otherwise
        # QProxyStyle will take ownership of it!
        style = settings.prefs.qtStyle
        super().__init__(style)

        self.richTextTable = {}

    def prepareRichLabel(self, markup: str, accelerator: str = ""):
        plain = stripHtml(markup)

        if accelerator:
            try:
                u = plain.lower().index(accelerator.lower())
                plain = plain[:u] + "&" + plain[u:]
            except LookupError:
                accelerator = ""

        doc = QTextDocument(self)
        doc.setHtml(markup)
        self.richTextTable[plain] = doc

        if accelerator:
            cursor = doc.find(accelerator)
            if not cursor.isNull():
                fmt = QTextCharFormat()
                fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SingleUnderline)
                cursor.mergeCharFormat(fmt)

        return plain

    def drawControl(self, element: QStyle.ControlElement, option: QStyleOption, painter: QPainter, widget: QWidget | None = None):
        if element == QStyle.ControlElement.CE_MenuItem:
            if not isinstance(option, QStyleOptionMenuItem):  # pragma: no cover - PyQt6 can be weird here, ignore
                super().drawControl(element, option, painter, widget)
                return

            plainText = option.text
            option.text = ""

            # Native background/selection (no text!)
            super().drawControl(element, option, painter, widget)

            textRect = QRect(option.rect)
            textRect.adjust(28 if option.menuHasCheckableItems else 0, 2, 0, -2)

            painter.save()
            painter.setClipRect(textRect)
            painter.translate(textRect.left(), textRect.top())
            doc = self.richTextTable[plainText]
            doc.setTextWidth(textRect.width())
            doc.drawContents(painter)
            painter.restore()
        else:
            super().drawControl(element, option, painter, widget)
