#!/usr/bin/env bash
set -e
scratch="$1"
shift
printf '%s\n' "$@" > "$scratch"
M="$1"
L="$2"
R="$3"
B="$4"
echo "merge complete!" > "$M"
