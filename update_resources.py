#! /usr/bin/env python3

import os, re, subprocess, sys

srcDir = "gitfourchette"
assetsDir = "assets"

for path in srcDir, assetsDir:
    if not os.path.isdir(path):
        print(F"Directory {path} not found; please run this script from the root of the repo")
        sys.exit(1)

def call(cmd, **kwargs) -> subprocess.CompletedProcess:
    cmdstr = ""
    for token in cmd:
        cmdstr += " "
        if " " in token:
            cmdstr += F"\"{token}\""
        else:
            cmdstr += token

    print(F">{cmdstr}")
    try:
        return subprocess.run(cmd, capture_output=True, encoding='utf-8', check=True, **kwargs)
    except subprocess.CalledProcessError as e:
        print(F"Aborting setup because: {e}")
        sys.exit(1)

def writeIfDifferent(path, text):
    if os.path.isfile(path):
        with open(path, 'r') as f:
            if f.read() == text:
                return
    with open(path, 'w') as f:
        f.write(text)

def writeStatusIcon(fill='#ff00ff', char='X', round=2):
    svg = "<svg xmlns='http://www.w3.org/2000/svg' width='16' height='16'>\n"
    svg += F"<rect rx='{round}' ry='{round}' x='0.5' y='0.5' width='15' height='15' stroke='white' stroke-width='1' fill='{fill}'/>\n"
    svg += F"<text x='8' y='12' font-weight='bold' font-size='11' font-family='sans-serif' text-anchor='middle' fill='white'>{char}</text>\n"
    svg += F"</svg>"
    svgFileName = F"{assetsDir}/status_{char.lower()}.svg"
    print(svgFileName)
    writeIfDifferent(svgFileName, svg)

# Generate status icons
# https://git-scm.com/docs/git-diff#_raw_output_format
writeStatusIcon('#0EDF00', 'A')  # add
writeStatusIcon('#000000', 'C')
writeStatusIcon('#FE635F', 'D')  # delete
writeStatusIcon('#F7C342', 'M')  # modify
writeStatusIcon('#D18DE1', 'R')  # renamed
writeStatusIcon('#000000', 'T')
writeStatusIcon('#90a0b0', 'U')  # unmerged
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
            result = call(["uic-qt5", "--generator", "python", fullpath])

            codeLines = ["from allqt import *", ""] + \
                        [line for line in result.stdout.splitlines()
                         if not line.startswith("from PySide2.")
                         and not line.startswith("# -*- coding:")]

            writeIfDifferent(F"{root}/ui_{basename}.py", "\n".join(codeLines))

for root, dirs, files in os.walk(assetsDir):
    for file in files:
        path = os.path.join(root, file)
        # Set a fixed mtime to make the contents of assets_rc.py deterministic
        os.utime(path, times=(0, 0))

# Generate assets_rc.py from assets.qrc
call(["rcc-qt5", "--generator", "python", F"{assetsDir}/assets.qrc", "--output", "gitfourchette/assets_rc.py"])
