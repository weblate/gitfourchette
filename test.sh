#!/usr/bin/env bash

set -ex

PYTHON=${PYTHON:-python3}
export PYTEST_QT_API=${PYTEST_QT_API:-pyside6}

$PYTHON -m pytest "$@"
echo "TESTS OK!"
