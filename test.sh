#!/usr/bin/env bash

set -ex
PYTEST_QT_API=${PYTEST_QT_API:-pyside2} python -m pytest "$@"
echo "TESTS OK!"
