#!/usr/bin/env bash

set -e

HERE="$(dirname "$(readlink -f -- "$0")" )"

thinlist=$(cat "$HERE/thinner.txt")
appdir="$1"

cd "$appdir"

for i in $thinlist
do
    echo Thinner: "$i"
    rm -rf "$i"
done
