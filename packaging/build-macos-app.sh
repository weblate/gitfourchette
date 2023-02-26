#!/bin/bash

set -ex

QT_API=pyside6 python3.11 -m PyInstaller packaging/gitfourchette-macos.spec --noconfirm

APP=dist/GitFourchette.app

# If macOS sees this file, AND the system's preferred language matches the language of
# "Edit" and "Help" menu titles, we'll automagically get stuff like a search field
# in the Help menu, or dictation stuff in the Edit menu.
# If this file is absent, the magic menu entries are only added if the menu names
# are in English.
touch $APP/Contents/Resources/empty.lproj

rm -fv $APP/Contents/MacOS/QtDataVisualization
rm -fv $APP/Contents/MacOS/QtOpenGL{,Widgets}
rm -fv $APP/Contents/MacOS/QtQml{,Models}
rm -fv $APP/Contents/MacOS/QtQuick
