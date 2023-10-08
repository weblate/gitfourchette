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

for component in QtNetwork QtOpenGL QtQml QtQmlModels QtQuick QtVirtualKeyboard
do
    echo "Removing $component"
    rm -fv $APP/Contents/Resources/$component
    rm -fv $APP/Contents/Frameworks/$component
    rm -rfv $APP/Contents/Frameworks/PySide6/Qt/lib/$component.framework
done
