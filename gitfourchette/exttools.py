import itertools
import logging
import os
import shlex

from gitfourchette import tempdir
from gitfourchette.qt import *
from gitfourchette.toolbox import *
from gitfourchette.trtables import TrTables

logger = logging.getLogger(__name__)

PREFKEY_EDITOR = "external_editor"
PREFKEY_DIFFTOOL = "external_diff"
PREFKEY_MERGETOOL = "external_merge"


def openPrefsDialog(parent: QWidget, prefKey: str):
    parent.window().openPrefsDialog(prefKey)


def onExternalToolProcessError(process: QProcess, prefKey: str):
    parent: QWidget = process.parent()
    assert isinstance(parent, QWidget)

    processError: QProcess.ProcessError = process.error()

    programName = process.program()
    programName = os.path.basename(programName)

    translatedPrefKey = TrTables.prefKey(prefKey)

    title = translate("exttools", "Failed to start {0}").format(translatedPrefKey)

    message = translate("exttools",
                        "Couldn’t start {0} {1} ({2}). "
                        "It might not be installed on your machine."
                        ).format(translatedPrefKey, bquo(programName), str(processError).removeprefix("ProcessError."))

    qmb = asyncMessageBox(parent, 'warning', title, message,
                          QMessageBox.StandardButton.Retry | QMessageBox.StandardButton.Ok)

    configureButton = qmb.button(QMessageBox.StandardButton.Retry)
    configureButton.setText(translate("exttools", "Pick another program"))

    def onQMBFinished(result):
        if result == QMessageBox.StandardButton.Retry:
            openPrefsDialog(parent, prefKey)

    qmb.finished.connect(onQMBFinished)
    qmb.show()


def setUpMergeToolPrompt(parent: QWidget, prefKey: str):
    translatedPrefKey = TrTables.prefKey(prefKey)

    title = translatedPrefKey

    message = translate("exttools", "{0} isn’t set up in your preferences yet.").format(bquo(translatedPrefKey))

    qmb = asyncMessageBox(parent, 'warning', title, message,
                          QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)

    configureButton = qmb.button(QMessageBox.StandardButton.Ok)
    configureButton.setText(translate("exttools", "Set up {0}").format(lquo(translatedPrefKey)))

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
        for p in positional:
            QDesktopServices.openUrl(QUrl.fromLocalFile(p))
        return

    if not command:
        setUpMergeToolPrompt(parent, prefKey)
        return

    tokens = shlex.split(command, posix=not WINDOWS)

    for placeholder, replacement in replacements.items():
        for i, tok in enumerate(tokens):
            if tok.endswith(placeholder):
                prefix = tok.removesuffix(placeholder)
                break
        else:
            raise ValueError(f"Placeholder token {placeholder} not found")
        if replacement:
            tokens[i] = prefix + replacement
        else:
            del tokens[i]

    # Just append other paths to end of command line...
    tokens.extend(positional)

    # Little trick to prevent opendiff (launcher shim for Xcode's FileMerge) from exiting immediately.
    # (Just launching /bin/bash -c ... doesn't make it wait)
    if os.path.basename(tokens[0]) == "opendiff":
        #tokens = ["/bin/bash", "-c", f"""'{tokens[0]}' "$@" | cat""", "--"] + tokens[1:]
        scriptPath = os.path.join(tempdir.getSessionTemporaryDirectory(), "opendiff.sh")
        with open(scriptPath, "w") as scriptFile:
            scriptFile.write(f"""#!/bin/sh\nset -e\n'{tokens[0]}' "$@" | cat""")
        os.chmod(scriptPath, 0o700)  # should be 500
        tokens = ["/bin/sh", scriptPath] + tokens[1:]

    wd = ""
    for p in itertools.chain(replacements.values(), positional):
        if not p:
            continue
        wd = os.path.dirname(p)
        break

    logger.info("Starting process: " + " ".join(tokens))

    p = QProcess(parent)
    p.setProgram(tokens[0])
    p.setArguments(tokens[1:])
    p.setWorkingDirectory(wd)
    p.setProcessChannelMode(QProcess.ProcessChannelMode.ForwardedChannels)

    p.finished.connect(lambda code, status: logger.info(f"Process done: {code} {status}"))
    p.errorOccurred.connect(lambda processError: logger.info(f"Process error: {processError}"))
    p.errorOccurred.connect(lambda processError: onExternalToolProcessError(p, prefKey))

    p.start(mode=QProcess.OpenModeFlag.Unbuffered)

    return p


def openInTextEditor(parent: QWidget, path: str):
    return openInExternalTool(parent, PREFKEY_EDITOR, positional=[path], replacements={},
                              allowQDesktopFallback=True)


def openInDiffTool(parent: QWidget, a: str, b: str):
    return openInExternalTool(parent, PREFKEY_DIFFTOOL, positional=[],
                              replacements={"$L": a, "$R": b})


def openInMergeTool(parent: QWidget, ancestor: str, ours: str, theirs: str, output: str):
    return openInExternalTool(parent, PREFKEY_MERGETOOL, positional=[],
                              replacements={"$B": ancestor, "$L": ours, "$R": theirs, "$M": output})
