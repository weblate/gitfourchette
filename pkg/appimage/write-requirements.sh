#!/usr/bin/env bash

set -e

export QT_API=${QT_API:-pyqt6}
HERE="$(dirname "$(readlink -f -- "$0")" )"
ROOT="$(readlink -f -- "$HERE/../..")"

echo -e "$ROOT\n$QT_API" > "$HERE/requirements.txt"
