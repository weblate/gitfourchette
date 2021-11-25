import os, sys, subprocess

uisrc_dir = "ui"
uigen_dir = "gitfourchette/ui"

if not os.path.isdir(uisrc_dir):
    print(F"Directory {uisrc_dir} not found; please run this script from the root of the repo")
    sys.exit(1)
if not os.path.isdir(uigen_dir):
    print(F"Directory {uigen_dir} not found; please run this script from the root of the repo")
    sys.exit(1)

# Delete all .py files in uigen_dir
for filename in (fn for fn in os.listdir(uigen_dir) if fn.endswith(".py")):
    fullpath = os.path.join(uigen_dir, filename)
    print(F"Deleting {fullpath}")
    os.remove(fullpath)

# Regenerate .py files
for filename in (fn for fn in os.listdir(uisrc_dir) if fn.endswith(".ui")):
    basename = os.path.splitext(filename)[0]
    fullpath = os.path.join(uisrc_dir, filename)
    genpath = os.path.join(uigen_dir, F"ui_{basename}.py")
    print(F"Generating {genpath}")
    result = subprocess.run(["pyside2-uic", fullpath, "--output", genpath])
    if result.returncode != 0:
        sys.exit(1)
