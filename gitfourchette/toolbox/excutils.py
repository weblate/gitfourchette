# -----------------------------------------------------------------------------
# Copyright (C) 2024 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

import os
import re
import traceback


def shortenTracebackPath(line):
    return re.sub(r'^\s*File "([^"]+)", line (\d+)',
                  lambda m: F'{os.path.basename(m.group(1))}:{m.group(2)}',
                  line, count=1)


def excStrings(exc):
    summary = traceback.format_exception_only(exc.__class__, exc)
    summary = ''.join(summary).strip()

    details = traceback.format_exception(exc.__class__, exc, exc.__traceback__)
    details = ''.join(details).strip()

    return summary, details
