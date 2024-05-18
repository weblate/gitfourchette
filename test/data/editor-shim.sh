#!/usr/bin/env bash
set -e
scratch="$1"
shift
echo $* > "$scratch"
