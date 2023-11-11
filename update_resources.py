#! /usr/bin/env python3
import argparse, difflib, os, re, subprocess, sys
import xml.etree.ElementTree as ET
from pathlib import Path

repoRootDir = os.path.dirname(os.path.realpath(sys.argv[0]))
repoRootDir = os.path.relpath(repoRootDir)
srcDir = os.path.join(repoRootDir, "gitfourchette")
langDir = os.path.join(repoRootDir, "lang")
assetsDir = os.path.join(srcDir, "assets")

parser = argparse.ArgumentParser(description="Update GitFourchette assets")
parser.add_argument("--force", action="store_true", help="skip mtime and equality checks before regenerating an asset")
parser.add_argument("--lang", action="store_true", default=False, help="update .ts/.qm files")
parser.add_argument("--clean-lang", action="store_true", default=False, help="update .ts/.qm files without source code info")
parser.add_argument("--lrelease", default="pyside6-lrelease", help="path to lrelease tool")
parser.add_argument("--lupdate", default="pyside6-lupdate", help="path to lupdate tool")
parser.add_argument("--uic", default="pyside6-uic", help="path to uic tool")
parser.add_argument("--version", action="store_true", default=False, help="show tool versions and exit")
cliArgs = parser.parse_args()

UIC = cliArgs.uic
LUPDATE = cliArgs.lupdate
LRELEASE = cliArgs.lrelease


def call(*args, **kwargs) -> subprocess.CompletedProcess:
    cmdstr = ""
    for token in args:
        cmdstr += " "
        if " " in token:
            cmdstr += F"\"{token}\""
        else:
            cmdstr += token
    print(F">{cmdstr}")

    capture_output = kwargs.pop("capture_output", True)
    check = kwargs.pop("check", True)
    try:
        return subprocess.run(args, encoding='utf-8', capture_output=capture_output, check=check, **kwargs)
    except subprocess.CalledProcessError as e:
        print(F"Aborting setup because: {e}")
        sys.exit(1)


if cliArgs.version:
    toolVersions = ""
    toolVersions += call(UIC, "--version").stdout
    toolVersions += call(LUPDATE, "-version").stdout
    toolVersions += call(LRELEASE, "-version").stdout
    print(toolVersions)
    sys.exit(0)


def writeIfDifferent(path, text, ignoreChangedLines=[]):
    needRewrite = True

    if not cliArgs.force:
        ignoreList = []
        for icl in ignoreChangedLines:
            ignoreList.append("+ " + icl)
            ignoreList.append("- " + icl)

        if os.path.isfile(path):
            with open(path, 'r') as existingFile:
                oldText = existingFile.read()

            # See if the differences can be ignored (e.g. Qt User Interface Compiler version comment)
            needRewrite = False
            if oldText != text:
                needRewrite = False
                t1 = oldText.splitlines(keepends=True)
                t2 = text.splitlines(keepends=True)
                for dl in difflib.ndiff(t1, t2):
                    if (dl.rstrip() not in ["+", "-"]  # pure whitespace change
                            and not dl.startswith(tuple(ignoreList))
                            and dl.startswith(("+ ", "- "))):
                        needRewrite = True
                        break

    if needRewrite:
        with open(path, 'w') as f:
            f.write(text)
            print("Wrote", path)
    else:
        Path(path).touch()


def writeStatusIcon(fill='#ff00ff', char='X', round=2):
    for suffix, color in (["", "white"], ["@dark", "black"]):
        svg = "<svg xmlns='http://www.w3.org/2000/svg' width='16' height='16'>\n"
        svg += f"<rect rx='{round}' ry='{round}' x='0.5' y='0.5' width='15' height='15' stroke='{color}' stroke-width='1' fill='{fill}'/>\n"
        svg += f"<text x='8' y='12' font-weight='bold' font-size='11' font-family='sans-serif' text-anchor='middle' fill='{color}'>{char}</text>\n"
        svg += f"</svg>"
        svgFileName = F"{assetsDir}/status_{char.lower()}{suffix}.svg"
        writeIfDifferent(svgFileName, svg)


def compileUi(uiPath, pyPath):
    if not cliArgs.force:
        uiStat = os.stat(uiPath)
        pyStat = os.stat(pyPath)
        if pyStat.st_mtime > uiStat.st_mtime:
            return

    result = call(UIC, "--generator", "python", uiPath)
    text = result.stdout

    text = re.sub(r"^# -\*- coding:.*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^from PySide2.* import .+$", "from gitfourchette.qt import *", text, count=1, flags=re.MULTILINE)
    text = re.sub(r"^from PySide6.* import \([^\)]+\)$", "from gitfourchette.qt import *", text, count=1, flags=re.MULTILINE)
    for nukePattern in [
            r"^# -\*- coding:.*$",
            r"^from PySide2.* import .+$\n",
            r"^from PySide6.* import \([^\)]+\)$\n",
            r"^ {4}# (setupUi|retranslateUi)$\n"]:
        text = re.sub(nukePattern, "", text, flags=re.MULTILINE)
    text = text.strip() + "\n"

    basename = os.path.splitext(file)[0]
    writeIfDifferent(pyPath, text,
                     ["## Created by: Qt User Interface Compiler version"])


# Generate status icons.
# 'U' (unmerged) has custom colors/text, so don't generate it automatically.
# 'C' (copied) and 'T' (typechange) don't appear in GitFourchette.
writeStatusIcon('#0EDF00', 'A')  # add
writeStatusIcon('#FE635F', 'D')  # delete
writeStatusIcon('#F7C342', 'M')  # modify
writeStatusIcon('#D18DE1', 'R')  # rename
writeStatusIcon('#ff00ff', 'X')  # unknown

# Generate .py files from .ui files
for root, dirs, files in os.walk(srcDir):
    for file in files:
        basename = os.path.splitext(file)[0]
        fullpath = os.path.join(root, file)

        if re.match(r"^ui_.+\.py$", file) and \
                not os.path.isfile(F"{root}/{basename.removeprefix('ui_')}.ui"):
            print("[!] Removing generated UI source file because there's no matching designer file:", fullpath)
            os.unlink(fullpath)
            continue

        if file.endswith(".ui"):
            compileUi(fullpath, F"{root}/ui_{basename}.py")


if cliArgs.lang or cliArgs.clean_lang:
    # Update .ts files from strings contained in the source code
    for file in os.listdir(langDir):
        if not file.endswith(".ts"):
            continue
        filePath = os.path.join(langDir, file)
        basename = os.path.splitext(file)[0]

        opts = "-extensions py,ui"
        if cliArgs.clean_lang:
            opts += " -no-ui-lines -no-obsolete -locations none"
        if file == "gitfourchette_en.ts":
            opts += " -pluralonly"

        call(LUPDATE, *opts.split(), srcDir, "-ts", filePath, capture_output=False)

    # Generate .qm files from .ts files
    anyPlaceholderMismatches = False
    for file in os.listdir(langDir):
        if not file.endswith(".ts"):
            continue
        filePath = os.path.join(langDir, file)
        basename = os.path.splitext(file)[0]
        qmPath = os.path.join(assetsDir, F"{basename}.qm")
        call(LRELEASE, "-removeidentical", filePath, "-qm", qmPath)

        # Check placeholders in .ts files
        for messageTag in ET.parse(filePath).getroot().findall('context/message'):
            sourceText = messageTag.findtext('source')
            sourcePlaceholders = set(re.findall(r"\{.*?\}", sourceText))
            if not sourcePlaceholders:
                continue

            translationText = messageTag.findtext('translation').strip()
            if translationText:
                translations = [translationText]
            else:
                translations = [t.text for t in messageTag.find('translation') if t.text and t.text.strip()]

            for tt in translations:
                translationPlaceholders = set(re.findall(r"\{.*?\}", tt))
                missingPlaceholders = sourcePlaceholders - translationPlaceholders
                if translationPlaceholders != sourcePlaceholders:
                    anyPlaceholderMismatches = True
                    print(f"******* {file}: PLACEHOLDER MISMATCH! "
                        f"Missing: {' '.join(s for s in missingPlaceholders)} "
                        f"in: \"{tt}\"")


    if not cliArgs.clean_lang:
        print("""
    *******************************************************************************
    You are using --lang, which generates extra info in the .ts files.
    Before committing the .ts files, please clean them up by running
    this script again with --clean-lang.
    *******************************************************************************
    """)

    if anyPlaceholderMismatches:
        print("""
    *******************************************************************************
    THE TRANSLATION FILES CONTAIN MISMATCHED PLACEHOLDERS.
    PLEASE REVIEW THE TRANSLATIONS BEFORE COMMITTING!
    *******************************************************************************
    """)
