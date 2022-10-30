#!/bin/bash

set -ex

pyinstaller packaging/gitfourchette-macos.spec --noconfirm

APP=dist/GitFourchette.app

# If macOS sees this file, AND the system's preferred language matches the language of
# "Edit" and "Help" menu titles, we'll automagically get stuff like a search field
# in the Help menu, or dictation stuff in the Edit menu.
# If this file is absent, the magic menu entries are only added if the menu names
# are in English.
touch $APP/Contents/Resources/empty.lproj

rm -v $APP/Contents/MacOS/QtDataVisualization
rm -v $APP/Contents/MacOS/QtOpenGL{,Widgets}
rm -v $APP/Contents/MacOS/QtQml{,Models}
rm -v $APP/Contents/MacOS/QtQuick
mv -v $APP/Contents/MacOS/libgit2.1.5{.0,}.dylib
