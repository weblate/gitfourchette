#!/usr/bin/env bash

set -e

HERE="$(dirname "$(readlink -f -- "$0")" )"
PYTHON=${PYTHON:-python3}
export PYTEST_QT_API=${PYTEST_QT_API:-pyqt6}
export QT_QPA_PLATFORM=${QT_QPA_PLATFORM:-offscreen}

if [[ $1 = "--cov" ]]; then
    echo "HTML coverage report enabled!"
    shift
    RUNNER="$PYTHON -m coverage run -m pytest"
    EPILOG="$PYTHON -m coverage html"
else
    echo "Coverage report disabled, pass --cov to enable"
    RUNNER="$PYTHON -m pytest"
    EPILOG=
fi

set -x
cd "$HERE"
time $RUNNER "$@"
echo "TESTS OK!"

[[ ! -z $EPILOG ]] && $EPILOG  # generate html coverage report
