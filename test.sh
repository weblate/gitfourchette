#!/usr/bin/env bash

PYTEST_QT_API=${PYTEST_QT_API:-pyside2} PYTHONPATH=gitfourchette python -m pytest $@
