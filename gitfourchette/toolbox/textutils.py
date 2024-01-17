import io
from typing import Iterable

from gitfourchette.qt import *
from html import escape as escape


_generalFontMetrics = QFontMetrics(QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont))


def messageSummary(body: str, elision=" […]"):
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
    if len(args) == 1 and type(args[0]) == list:
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


def elide(text: str, mode: Qt.TextElideMode = Qt.TextElideMode.ElideMiddle, ems: int = 20):
    maxWidth = _generalFontMetrics.horizontalAdvance(ems * 'M')
    return _generalFontMetrics.elidedText(text, mode, maxWidth)


def clipboardStatusMessage(text: str):
    n = 1 + text.count('\n')
    if n == 1:
        return tr("“{0}” copied to clipboard.").format(elide(text))
    else:
        return tr("%n lines copied to clipboard.", "", n)


def ulList(items: Iterable[str], limit: int = 10):
    n = 0
    text = "<ul>"

    for item in items:
        if n < limit:
            text += f"\n<li>{item}</li>"
        n += 1

    if n == 0:
        return ""

    if n > limit:
        unlisted = n - limit
        more = translate("Global", "(+ %n more)", "", unlisted)
        text += f"\n<li><i>{more}</i></li>"

    text += "\n</ul>"
    return text

