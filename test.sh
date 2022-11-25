#!/usr/bin/env bash

set -ex
PYTEST_QT_API=${PYTEST_QT_API:-pyside6} python3 -m pytest "$@"
echo "TESTS OK!"
