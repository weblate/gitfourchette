# -----------------------------------------------------------------------------
# Copyright (C) 2024 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

import itertools
import os
import shlex
from collections.abc import Sequence

from gitfourchette.qt import *


class ToolCommands:
    DefaultDiffPreset = ""
    DefaultMergePreset = ""
    FlatpakNamePrefix = "Flatpak: "

    EditorPresets = {
        "System default": "",
        "BBEdit"        : "bbedit",
        "GVim"          : "gvim",
        "Kate"          : "kate",
        "KWrite"        : "kwrite",
        "MacVim"        : "mvim",
        "VS Code"       : "code",
    }

    DiffPresets = {
        "Beyond Compare": "bcompare $L $R",
        "CLion"         : "clion diff $L $R",
        "DiffMerge"     : "diffmerge $L $R",
        "FileMerge"     : "opendiff $L $R",
        "GVim"          : "gvim -f -d $L $R",
        "IntelliJ IDEA" : "idea diff $L $R",
        "KDiff3"        : "kdiff3 $L $R",
        "MacVim"        : "mvim -f -d $L $R",
        "Meld"          : "meld $L $R",
        "P4Merge"       : "p4merge $L $R",
        "PyCharm"       : "pycharm diff $L $R",
        "VS Code"       : "code --new-window --wait --diff $L $R",
        "WinMerge"      : "winmergeu /u /wl /wr $L $R",
    }

    # $B: ANCESTOR/BASE/CENTER
    # $L: OURS/LOCAL/LEFT
    # $R: THEIRS/REMOTE/RIGHT
    # $M: MERGED/OUTPUT
    MergePresets = {
        "Beyond Compare": "bcompare $L $R $B $M",
        "CLion"         : "clion merge $L $R $B $M",
        "DiffMerge"     : "diffmerge --merge --result=$M $L $B $R",
        "FileMerge"     : "opendiff -ancestor $B $L $R -merge $M",
        "GVim"          : "gvim -f -d -c 'wincmd J' $M $L $B $R",
        "IntelliJ IDEA" : "idea merge $L $R $B $M",
        "KDiff3"        : "kdiff3 --merge $B $L $R --output $M",
        "MacVim"        : "mvim -f -d -c 'wincmd J' $M $L $B $R",
        "Meld"          : "meld --auto-merge $L $B $R --output=$M",
        "P4Merge"       : "p4merge $B $L $R $M",
        "PyCharm"       : "pycharm merge $L $R $B $M",
        "VS Code"       : "code --new-window --wait --merge $L $R $B $M",
        "WinMerge"      : "winmergeu /u /wl /wm /wr /am $B $L $R /o $M",
    }

    @classmethod
    def _filterToolPresets(cls):  # pragma: no cover
        freedesktopTools = ["Kate", "KWrite"]
        macTools = ["FileMerge", "MacVim", "BBEdit"]
        winTools = ["WinMerge"]
        allPresetDicts = [cls.EditorPresets, cls.DiffPresets, cls.MergePresets]

        if MACOS:
            excludeTools = winTools + freedesktopTools
            cls.DefaultDiffPreset = "FileMerge"
            cls.DefaultMergePreset = "FileMerge"
        elif WINDOWS:
            excludeTools = macTools + freedesktopTools
            cls.DefaultDiffPreset = "WinMerge"
            cls.DefaultMergePreset = "WinMerge"
        else:
            excludeTools = macTools + winTools
            cls.DefaultDiffPreset = "Meld"
            cls.DefaultMergePreset = "Meld"

        for key in excludeTools:
            for presets in allPresetDicts:
                try:
                    del presets[key]
                except KeyError:
                    pass

    @classmethod
    def getCommandName(cls, command: str, fallback = "", presets: dict[str, str] | None = None) -> str:
        if not command.strip():
            return fallback

        if presets is not None:
            presetName = next((k for k, v in presets.items() if v == command), "")
            if presetName:
                if presetName.startswith(cls.FlatpakNamePrefix):
                    presetName = presetName.removeprefix(cls.FlatpakNamePrefix)
                    presetName += " (Flatpak)"
                return presetName

        tokens = shlex.split(command, posix=not WINDOWS)

        try:
            name = tokens[0]
        except IndexError:
            return fallback

        name = name.removeprefix('"').removeprefix("'")
        name = name.removesuffix('"').removesuffix("'")
        name = os.path.basename(name)

        if MACOS:
            name = name.removesuffix(".app")

        return name

    @classmethod
    def replaceProgramTokenInCommand(cls, command: str, *newProgramTokens: str):
        tokens = shlex.split(command, posix=not WINDOWS)
        tokens = list(newProgramTokens) + tokens[1:]

        newCommand = shlex.join(tokens)

        # Remove single quotes added around our placeholders by shlex.join()
        # (e.g. '$L' --> $L, '--output=$M' --> $M)
        import re
        newCommand = re.sub(r" '(\$[0-9A-Z])'", r" \1", newCommand, flags=re.I | re.A)
        newCommand = re.sub(r" '(--?[a-z]+=\$[0-9A-Z])'", r" \1", newCommand, flags=re.I | re.A)

        return newCommand

    @classmethod
    def checkCommand(cls, command: str, *placeholders: str):
        try:
            cls.compileCommand(command, {k: "PLACEHOLDER" for k in placeholders}, [])
            return ""
        except ValueError as e:
            return str(e)

    @classmethod
    def compileCommand(cls, command: str, replacements: dict[str, str], positional: list[str]):
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

        # Find appropriate workdir
        workingDirectory = ""
        for argument in itertools.chain(replacements.values(), positional):
            if not argument:
                continue
            workingDirectory = os.path.dirname(argument)
            if os.path.isdir(workingDirectory):
                break

        # macOS-specific wrapper:
        # - Launch ".app" bundles properly.
        # - Wait on opendiff (Xcode FileMerge).
        if MACOS:
            launcherScript = QFile("assets:mactool.sh")
            assert launcherScript.exists()
            tokens.insert(0, launcherScript.fileName())

        # Flatpak-specific wrapper:
        # - Run external tool outside flatpak sandbox.
        # - Set workdir via flatpak-spawn because QProcess.setWorkingDirectory won't work.
        # - Run command through `env` to get return code 127 if the command is missing.
        if FLATPAK:
            spawner = [
                "flatpak-spawn", "--watch-bus", "--host", f"--directory={workingDirectory}",
                "/usr/bin/env", "--"
            ]
            tokens = spawner + tokens

        return tokens, workingDirectory


ToolCommands._filterToolPresets()
