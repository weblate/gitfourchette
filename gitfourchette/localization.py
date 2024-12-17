# -----------------------------------------------------------------------------
# Copyright (C) 2024 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

from gettext import GNUTranslations
from gettext import NullTranslations


_translator = NullTranslations()

def installGettextTranslator(path: str):
    global _translator
    try:
        with open(path, 'rb') as fp:
            _translator = GNUTranslations(fp)
    except OSError:
        _translator = NullTranslations()

def _(message: str) -> str:
    return _translator.gettext(message)

def _n(singular: str, plural: str, n: int, *args, **kwargs) -> str:
    return _translator.ngettext(singular, plural, n).format(*args, **kwargs, n=n)

def _np(context: str, singular: str, plural: str, n: int) -> str:
    return _translator.npgettext(context, singular, plural, n).format(n=n)

def _p(context: str, message: str) -> str:
    return _translator.pgettext(context, message)


__all__ = [
    "_",
    "_n",
    "_np",
    "_p",
    "installGettextTranslator",
]
