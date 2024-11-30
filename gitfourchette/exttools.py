# -----------------------------------------------------------------------------
# Copyright (C) 2024 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

import itertools
import logging
import os
import re
import shlex

from gitfourchette.qt import *
from gitfourchette.settings import prefs, TEST_MODE
from gitfourchette.toolbox import *
from gitfourchette.trtables import TrTables

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

    tokens = shlex.split(command, posix=not WINDOWS)
    tokens[0] = newPath

    newCommand = shlex.join(tokens)

    # Remove single quotes added around our placeholders by shlex.join() (e.g. $L --> '$L')
    newCommand = re.sub(r" '(\$[0-9A-Z])'", r" \1", newCommand, flags=re.I | re.A)

    setattr(prefs, prefKey, newCommand)
    prefs.write()


def onExternalToolProcessError(parent: QWidget, prefKey: str):
    assert isinstance(parent, QWidget)

    commandTokens = shlex.split(getattr(prefs, prefKey), posix=not WINDOWS)
    programName = os.path.basename(commandTokens[0])

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


def setUpMergeToolPrompt(parent: QWidget, prefKey: str):
    translatedPrefKey = TrTables.prefKey(prefKey)

    title = translatedPrefKey

    message = translate("exttools", "{0} isn’t configured in your settings yet.").format(bquo(translatedPrefKey))

    qmb = asyncMessageBox(parent, 'warning', title, message,
                          QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)

    configureButton = qmb.button(QMessageBox.StandardButton.Ok)
    configureButton.setText(translate("exttools", "Set up {0}").format(lquo(translatedPrefKey)))

    qmb.accepted.connect(lambda: openPrefsDialog(parent, prefKey))
    qmb.show()


def validateExternalToolCommand(command: str, *placeholders: str):
    try:
        buildExternalToolCommand(command, {k: "PLACEHOLDER" for k in placeholders}, [])
        return ""
    except ValueError as e:
        return str(e)


def buildExternalToolCommand(command: str, replacements: dict[str, str], positional: list[str]):
    tokens = shlex.split(command, posix=not WINDOWS)

    for placeholder, replacement in replacements.items():
        for i, tok in enumerate(tokens):  # noqa: B007
            if tok.endswith(placeholder):
                prefix = tok.removesuffix(placeholder)
                break
        else:
            raise ValueError(translate("exttools", "Placeholder token {0} missing.").format(placeholder))
        if replacement:
            tokens[i] = prefix + replacement
        else:
            del tokens[i]

    # Just append other paths to end of command line...
    tokens.extend(positional)

    return tokens


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
        setUpMergeToolPrompt(parent, prefKey)
        return None

    # Find appropriate workdir
    workingDirectory = ""
    for argument in itertools.chain(replacements.values(), positional):
        if not argument:
            continue
        workingDirectory = os.path.dirname(argument)
        break

    tokens = buildExternalToolCommand(command, replacements, positional)

    wrapper = []

    # macOS-specific wrapper:
    # - Launch ".app" bundles properly.
    # - Wait on opendiff (Xcode FileMerge).
    if MACOS:
        launcherScript = QFile("assets:mactool.sh")
        assert launcherScript.exists()
        wrapper = [launcherScript.fileName()]

    # Flatpak-specific wrapper:
    # - Run external tool outside flatpak sandbox.
    # - Set workdir via flatpak-spawn because QProcess.setWorkingDirectory won't work.
    # - Run command through `env` to get return code 127 if the command is missing.
    if FLATPAK:
        wrapper = ["flatpak-spawn", "--watch-bus", "--host", f"--directory={workingDirectory}", "/usr/bin/env", "--"]

    tokens = wrapper + tokens

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
