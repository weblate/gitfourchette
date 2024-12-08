# -----------------------------------------------------------------------------
# Copyright (C) 2024 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

import logging
import shlex

from gitfourchette.qt import *
from gitfourchette.settings import prefs, TEST_MODE
from gitfourchette.toolbox import *
from gitfourchette.trtables import TrTables
from gitfourchette.toolcommands import ToolCommands

logger = logging.getLogger(__name__)

PREFKEY_EDITOR = "externalEditor"
PREFKEY_DIFFTOOL = "externalDiff"
PREFKEY_MERGETOOL = "externalMerge"


def openPrefsDialog(parent: QWidget, prefKey: str):
    from gitfourchette.mainwindow import MainWindow
    while parent:
        if isinstance(parent, MainWindow):
            parent.openPrefsDialog(prefKey)
            break
        else:
            parent = parent.parentWidget()


def onLocateTool(prefKey: str, newPath: str):
    command = getattr(prefs, prefKey)
    newCommand = ToolCommands.replaceProgramTokenInCommand(command, newPath)
    setattr(prefs, prefKey, newCommand)
    prefs.write()


def onExternalToolProcessError(parent: QWidget, prefKey: str):
    assert isinstance(parent, QWidget)

    programName = ToolCommands.getCommandName(getattr(prefs, prefKey), "", {})

    translatedPrefKey = TrTables.prefKey(prefKey)

    title = translate("exttools", "Failed to start {0}").format(translatedPrefKey)

    message = translate("exttools",
                        "Couldn’t start {command} ({what}). It might not be installed on your machine."
                        ).format(what=translatedPrefKey, command=bquo(programName))

    configureButtonID = QMessageBox.StandardButton.Ok
    browseButtonID = QMessageBox.StandardButton.Open

    qmb = asyncMessageBox(parent, 'warning', title, message,
                          configureButtonID | browseButtonID | QMessageBox.StandardButton.Cancel)

    configureButton = qmb.button(configureButtonID)
    configureButton.setText(translate("exttools", "Change tools..."))
    configureButton.setIcon(stockIcon("configure"))

    browseButton = qmb.button(browseButtonID)
    browseButton.setText(translate("exttools", "Locate {0}...").format(lquo(programName)))

    def onQMBFinished(result):
        if result == configureButtonID:
            openPrefsDialog(parent, prefKey)
        elif result == browseButtonID:
            qfd = QFileDialog(parent, translate("exttools", "Where is {0}?").format(lquo(programName)))
            qfd.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
            qfd.setFileMode(QFileDialog.FileMode.AnyFile)
            qfd.setWindowModality(Qt.WindowModality.WindowModal)
            qfd.setOption(QFileDialog.Option.DontUseNativeDialog, TEST_MODE)
            qfd.show()
            qfd.fileSelected.connect(lambda newPath: onLocateTool(prefKey, newPath))
            return qfd

    qmb.finished.connect(onQMBFinished)
    qmb.show()


def setUpToolCommand(parent: QWidget, prefKey: str):
    translatedPrefKey = TrTables.prefKey(prefKey)

    title = translatedPrefKey

    message = translate("exttools", "{0} isn’t configured in your settings yet."
                        ).format(bquo(translatedPrefKey))

    qmb = asyncMessageBox(parent, 'warning', title, message,
                          QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)

    configureButton = qmb.button(QMessageBox.StandardButton.Ok)
    configureButton.setText(translate("exttools", "Set up {0}"
                                      ).format(lquo(translatedPrefKey)))

    qmb.accepted.connect(lambda: openPrefsDialog(parent, prefKey))
    qmb.show()


def openInExternalTool(
        parent: QWidget,
        prefKey: str,
        replacements: dict[str, str],
        positional: list[str],
        allowQDesktopFallback: bool = False
) -> QProcess | None:

    assert isinstance(parent, QWidget)

    from gitfourchette import settings

    command = getattr(settings.prefs, prefKey, "").strip()

    if not command and allowQDesktopFallback:
        for argument in positional:
            QDesktopServices.openUrl(QUrl.fromLocalFile(argument))
        return None

    if not command:
        setUpToolCommand(parent, prefKey)
        return None

    tokens, workingDirectory = ToolCommands.compileCommand(command, replacements, positional)

    process = QProcess(parent)
    process.setProgram(tokens[0])
    process.setArguments(tokens[1:])
    if not FLATPAK:  # In Flatpaks, set workdir via flatpak-spawn
        process.setWorkingDirectory(workingDirectory)
    process.setProcessChannelMode(QProcess.ProcessChannelMode.ForwardedChannels)

    def wrap127(code, status):
        logger.info(f"Process done: {code} {status}")
        if not WINDOWS and code == 127:
            onExternalToolProcessError(parent, prefKey)

    process.finished.connect(wrap127)
    process.errorOccurred.connect(lambda processError: logger.info(f"Process error: {processError}"))
    process.errorOccurred.connect(lambda processError: onExternalToolProcessError(parent, prefKey))

    logger.info("Starting process: " + shlex.join(tokens))
    process.start(mode=QProcess.OpenModeFlag.Unbuffered)

    return process


def openInTextEditor(parent: QWidget, path: str):
    return openInExternalTool(parent, PREFKEY_EDITOR, positional=[path], replacements={},
                              allowQDesktopFallback=True)


def openInDiffTool(parent: QWidget, a: str, b: str):
    return openInExternalTool(parent, PREFKEY_DIFFTOOL, positional=[],
                              replacements={"$L": a, "$R": b})
