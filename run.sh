#!/usr/bin/env bash

set -e

PYTHON=${PYTHON:-python3}
export PYTHONPATH="$(dirname "$0")"
export QT_API=${QT_API:-pyqt6}

$PYTHON -m gitfourchette "$@"
