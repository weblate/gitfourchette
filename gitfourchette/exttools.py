from gitfourchette.qt import *
from gitfourchette.toolbox import *
from gitfourchette import tempdir
import os
import shlex


def openInExternalTool(
        parent: QWidget,
        prefKey: str,
        paths: list[str],
        allowQDesktopFallback: bool = False):

    from gitfourchette import settings

    command = getattr(settings.prefs, prefKey, "").strip()

    if not command and allowQDesktopFallback:
        for p in paths:
            QDesktopServices.openUrl(QUrl.fromLocalFile(p))
        return

    if not command:
        translatedPrefKey = prefKey  # TODO: access PrefsDialog.settingsTranslationTable
        showWarning(
            parent,
            translatedPrefKey,
            translate("Global", "Please set up “{0}” in the Preferences.").format(translatedPrefKey))
        return

    tokens = shlex.split(command, posix=not WINDOWS)

    for i, path in enumerate(paths, start=1):
        placeholderIndex = tokens.index(f"${i}")
        if path:
            tokens[placeholderIndex] = path
        else:
            del tokens[placeholderIndex]

    # Little trick to prevent opendiff (launcher shim for Xcode's FileMerge) from exiting immediately.
    # (Just launching /bin/bash -c ... doesn't make it wait)
    if os.path.basename(tokens[0]) == "opendiff":
        #tokens = ["/bin/bash", "-c", f"""'{tokens[0]}' "$@" | cat""", "--"] + tokens[1:]
        scriptPath = os.path.join(tempdir.getSessionTemporaryDirectory(), "opendiff.sh")
        with open(scriptPath, "w") as scriptFile:
            scriptFile.write(f"""#!/bin/sh\nset -e\n'{tokens[0]}' "$@" | cat""")
        os.chmod(scriptPath, 0o700)  # should be 500
        tokens = ["/bin/sh", scriptPath] + tokens[1:]

    print("Starting process:", " ".join(tokens))

    p = QProcess(parent)
    p.setProgram(tokens[0])
    p.setArguments(tokens[1:])
    p.setWorkingDirectory(os.path.dirname(paths[0]))
    p.setProcessChannelMode(QProcess.ProcessChannelMode.ForwardedChannels)
    p.finished.connect(lambda code, status: print("Process done:", code, status))
    p.start(mode=QProcess.OpenModeFlag.Unbuffered)

    if p.state() == QProcess.ProcessState.NotRunning:
        print("Failed to start?")

    waitToStart = p.waitForStarted(msecs=10000)
    if not waitToStart:
        print("Failed to start?")

    return p


def openInTextEditor(parent: QWidget, path: str):
    return openInExternalTool(parent, "external_editor", [path], allowQDesktopFallback=True)


def openInDiffTool(parent: QWidget, a: str, b: str):
    return openInExternalTool(parent, "external_diff", [a, b])


def openInMergeTool(parent: QWidget, ancestor: str, ours: str, theirs: str, output: str):
    return openInExternalTool(parent, "external_merge", [ancestor, ours, theirs, output])
