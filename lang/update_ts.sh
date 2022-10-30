#!/bin/bash

set -ex

LUPDATE=pyside6-lupdate
SRCDIR=../gitfourchette

LUPDATE_OPTS="-extensions py,ui"

cd "$(dirname "$0")"

"$LUPDATE" $LUPDATE_OPTS -pluralonly "$SRCDIR" -ts en.ts
"$LUPDATE" $LUPDATE_OPTS "$SRCDIR" -ts fr.ts
