#!/usr/bin/env bash

set -e

HERE="$(dirname "$(readlink -f -- "$0")" )"
PYTHON=${PYTHON:-python3}
export PYTEST_QT_API=${PYTEST_QT_API:-pyqt6}
export QT_QPA_PLATFORM=offscreen

RUNNER="$PYTHON -m pytest -n auto --dist worksteal"

if [[ $1 = "--cov" ]]; then
    shift
    RUNNER+=" --cov=gitfourchette --cov-report=html"
else
    echo "Coverage report disabled, pass --cov to enable"
fi

cd "$HERE"
$RUNNER "$@"

