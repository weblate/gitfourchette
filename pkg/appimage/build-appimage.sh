 #!/usr/bin/env bash

set -e
set -x

export QT_API=${QT_API:-pyqt6}
export PYVER=${PYVER:-"3.12"}

HERE="$(dirname "$(readlink -f -- "$0")" )"
ROOT="$(readlink -f -- "$HERE/../..")"

mkdir -p "$ROOT/build"
cd "$ROOT/build"

# Freeze QT api
"$ROOT/update_resources.py" --freeze $QT_API

# Write requirements file so python_appimage knows what to include.
# The path to gitfourchette's root dir must be absolute.
echo -e "$ROOT\n$QT_API" > "$HERE/requirements.txt"

# Create AppImage
python -m python_appimage -v build app -p $PYVER "$HERE"

# Post-process the AppImage
mv GitFourchette-*.AppImage FullFat.AppImage
rm -rf squashfs-root  # remove existing squashfs-root from previous run
./FullFat.AppImage --appimage-extract  # extract contents to squashfs-root

# Remove junk that we don't need
pushd squashfs-root
junklist=$(cat "$HERE/junklist.txt")
rm -rfv $junklist
popd

# Repackage the AppImage
appimagetool --no-appstream squashfs-root
chmod +x GitFourchette*.AppImage
