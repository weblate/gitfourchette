# -----------------------------------------------------------------------------
# Copyright (C) 2026 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

from pathlib import Path

from gitfourchette.forms.rebasedialog import RebaseDialog
from gitfourchette.localization import *
from gitfourchette.porcelain import RefPrefix
from gitfourchette.qt import *
from gitfourchette.rebase.rebasemodel import parseRebaseTodo
from gitfourchette.toolbox import tquo, tquoe, shortHash


def makeDialog():
    app = QApplication.instance()

    parser = QCommandLineParser()
    parser.setApplicationDescription(qAppName() + " - " + _("Rebase sequence editor"))
    parser.addHelpOption()
    parser.addVersionOption()
    parser.addOption(QCommandLineOption("message"))
    parser.addPositionalArgument("git-rebase-todo", _("Path to temporary file passed by {0}", tquo("git rebase")), "[repos...]")
    parser.process(app.arguments())

    if parser.isSet("message"):
        print("TODO: message mode?", app.arguments())
        app.exit(1)
        return

    path = parser.positionalArguments()[0]
    text = Path(path).read_text(encoding="utf-8")
    sequence = parseRebaseTodo(text)

    dialog = RebaseDialog(None, sequence)
    dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    dialog.accepted.connect(lambda: dialog.writeSequenceFile(path))
    dialog.rejected.connect(lambda: dialog.writeEmptySequenceFile(path))#app.exit(1))

    # TODO: Can we get those from pygit2?
    try:
        headName = Path(path).with_name("head-name").read_text("utf-8").strip()
        _dummy, headName = RefPrefix.split(headName)
    except OSError:
        headName = ""
    try:
        onto = Path(path).with_name("onto").read_text("utf-8").strip()
        if all(c in "0123456789abcdef" for c in onto):
            onto = shortHash(onto)
    except OSError:
        onto = ""
    if headName and onto:
        dialog.setWindowTitle(_("Rebase {0} onto {1}", tquoe(headName), tquoe(onto)))

    dialog.show()
    return dialog


def main():
    from gitfourchette.application import GFApplication
    import sys
    app = GFApplication(sys.argv, barebones=True)
    _dontCollectMe = makeDialog()
    returnCode = app.exec()
    return sys.exit(returnCode)


if __name__ == '__main__':
    main()
