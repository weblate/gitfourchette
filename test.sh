#!/usr/bin/env bash

set -e

HERE="$(dirname "$(readlink -f -- "$0")" )"
PYTHON=${PYTHON:-python3}
export PYTEST_QT_API=${PYTEST_QT_API:-pyqt6}
export QT_QPA_PLATFORM=${QT_QPA_PLATFORM:-offscreen}
COVERAGE=0

if [[ $1 = "--cov" ]]; then
    shift
    RUNNER="$PYTHON -m coverage run -m pytest"
    COVERAGE=1
else
    echo "Coverage report disabled, pass --cov to enable"
    RUNNER="$PYTHON -m pytest"
fi

cd "$HERE"
$RUNNER "$@"

if [[ $COVERAGE -ne 0 ]]; then
    # Generate HTML coverage report
    $PYTHON -m coverage report | grep TOTAL
    $PYTHON -m coverage html
fi
