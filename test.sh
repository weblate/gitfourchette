#!/usr/bin/env bash

set -ex

PYTHON=${PYTHON:-python3}
export PYTEST_QT_API=${PYTEST_QT_API:-pyqt6}

cd "$(dirname "$0")"

QT_QPA_PLATFORM=offscreen $PYTHON -m pytest "$@"
echo "TESTS OK!"
