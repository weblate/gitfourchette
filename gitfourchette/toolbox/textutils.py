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
    and returns the concatenated P tags.
    """

    # If passed an actual list object, use that as the argument list.
    if len(args) == 1 and type(args[0]) == list:
        args = args[0]

    return "<p>" + "</p><p>".join(args) + "</p>"


def elide(text: str, ems: int = 20):
    maxWidth = _generalFontMetrics.horizontalAdvance(ems * 'M')
    return _generalFontMetrics.elidedText(text, Qt.TextElideMode.ElideMiddle, maxWidth)


