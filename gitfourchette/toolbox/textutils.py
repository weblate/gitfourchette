# -----------------------------------------------------------------------------
# Copyright (C) 2024 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

import html
import io
import re
from collections.abc import Iterable, Callable, Container
from html import escape as escape

from gitfourchette.qt import *

_elideMetrics: QFontMetrics | None = None

_naturalSortSplit = re.compile(r"(\d+)")


def getElideMetrics() -> QFontMetrics:
    # Cannot initialize _elideMetrics too early for Windows offscreen unit tests
    global _elideMetrics
    if _elideMetrics is None:
        _elideMetrics = QFontMetrics(QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont))
    return _elideMetrics


def messageSummary(body: str, elision=" [\u2026]"):
    messageContinued = False
    message: str = body.strip()
    newline = message.find('\n')
    if newline > -1:
        messageContinued = newline < len(message) - 1
        message = message[:newline]
        if messageContinued:
            message += elision
    return message, messageContinued


# Ampersands from user strings must be sanitized for QLabel.
def escamp(text: str) -> str:
    return text.replace('&', '&&')


def paragraphs(*args) -> str:
    """
    Surrounds each argument string with an HTML "P" tag
    (or BLOCKQUOTE if the argument starts with the tab character)
    and returns a concatenated string of HTML tags.
    """

    # If passed an actual list object, use that as the argument list.
    if len(args) == 1 and isinstance(args[0], list):
        args = args[0]

    builder = io.StringIO()
    for arg in args:
        if arg.startswith("\t"):
            builder.write("<blockquote>")
            builder.write(arg)
            builder.write("</blockquote>")
        else:
            builder.write("<p>")
            builder.write(arg)
            builder.write("</p>")

    return builder.getvalue()


def _quotePattern(text, htm=True):
    q = tr("“{0}”", "Typographic quotes in your language. "
                    "Will surround user strings throughout the app.")
    if not htm:
        q = html.unescape(q)
    return q.format(text)


def hquo(text: str):
    """ Quote HTML-safe. """
    text = escape(text)
    text = _quotePattern(text)
    return text


def hquoe(text: str):
    """ Quote HTML-safe elide. """
    text = elide(text)
    text = escape(text)
    text = _quotePattern(text)
    return text


def bquo(text: str):
    """ Quote bold HTML-safe. """
    text = escape(text)
    text = f"<b>{text}</b>"
    text = _quotePattern(text)
    return text


def bquoe(text):
    """ Quote bold HTML-safe elide. """
    text = elide(text)
    text = escape(text)
    text = f"<b>{text}</b>"
    text = _quotePattern(text)
    return text


def lquo(text):
    """ Quote ampersand-safe. """
    text = escamp(text)
    text = _quotePattern(text, htm=False)
    return text


def lquoe(text):
    """ Quote ampersand-safe elide. """
    text = elide(text)
    text = escamp(text)
    text = _quotePattern(text, htm=False)
    return text


def tquo(text):
    """ Quote plain text. """
    text = _quotePattern(text, htm=False)
    return text


def tquoe(text):
    """ Quote plain text. """
    text = elide(text)
    text = _quotePattern(text, htm=False)
    return text


def btag(text):
    text = escape(text)
    text = f"<b>{text}</b>"
    return text


def stripHtml(markup: str):
    return QTextDocumentFragment.fromHtml(markup).toPlainText()


def elide(text: str, mode: Qt.TextElideMode = Qt.TextElideMode.ElideMiddle, ems: int = 20):
    metrics = getElideMetrics()
    maxWidth = metrics.horizontalAdvance(ems * 'M')
    return metrics.elidedText(text, mode, maxWidth)


def clipboardStatusMessage(text: str):
    n = 1 + text.count('\n')
    if n == 1:
        return tr("{0} copied to clipboard.").format(tquoe(text))
    else:
        return tr("%n lines copied to clipboard.", "", n)


def ulify(items: Iterable[str], limit: int = 10, prefix="", suffix="", moreText=""):
    n = 0
    text = "<ul>"

    for item in items:
        if limit < 0 or n < limit:
            text += f"\n<li>{prefix}{item}{suffix}</li>"
        n += 1

    if n == 0:
        return ""

    if 0 <= limit < n:
        unlisted = n - limit
        if not moreText:
            moreText = tr("...and {0} more")
        moreText = moreText.format(unlisted)
        text += f"\n<li>{prefix}<i>{moreText}</i>{suffix}</li>"

    text += "\n</ul>"
    return text


def toTightUL(items: Iterable[str], limit=10, moreText=""):
    return ulify(items, limit=limit, moreText=moreText)


def toRoomyUL(items: Iterable[str]):
    return ulify(items, -1, "<p>", "</p>")


def linkify(text, *hrefs: str | QUrl):
    hrefs = [h.toString() if isinstance(h, QUrl) else h for h in hrefs]

    assert all('"' not in href for href in hrefs)

    if "[" not in text:
        assert len(hrefs) == 1
        return f"<a href=\"{hrefs[0]}\">{text}</a>"

    for href in hrefs:
        assert "[" in text
        text = text.replace("[", f"<a href=\"{href}\">", 1).replace("]", "</a>", 1)

    return text


def tagify(text, *tags: str):
    def closingTag(tag: str):
        rtags = tag.split("<")[1:]
        rtags.append("")
        return "</".join(reversed(rtags))

    if "[" not in text:
        assert "]" not in text
        text = f"[{text}]"

    for tag in tags:
        text = text.replace("[", tag, 1).replace("]", closingTag(tag), 1)

    return text


def withUniqueSuffix(
        stem: str, reserved: Container[str] | Callable[[str], bool],
        start=2, stop=-1,
        ext="", suffixFormat="-{}"):
    # Test format first to catch any errors even if we don't enter the loop
    assert suffixFormat.format(1) != suffixFormat.format(2), "illegal suffixFormat"

    name = stem + ext
    i = start

    if not callable(reserved):
        isTaken = reserved.__contains__
    else:
        isTaken = reserved

    while isTaken(name):
        name = stem + suffixFormat.format(i) + ext
        i += 1
        if stop >= 0 and i > stop:
            break

    return name


def englishTitleCase(text: str) -> str:
    if QLocale().language() in [QLocale.Language.C, QLocale.Language.English]:
        text = text.title()
    return text


def naturalSort(text: str):
    text = text.casefold()
    parts = _naturalSortSplit.split(text)
    return [int(part) if part.isdigit() else part for part in parts]
