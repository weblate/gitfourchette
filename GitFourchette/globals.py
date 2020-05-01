from PySide2.QtWidgets import *
from PySide2.QtGui import *
from PySide2.QtCore import *
import git

TAB_SPACES = 4

VERSION = "0.1-preview"

PROGRAM_NAME = "GitFourchette🅪"

PROGRAM_ABOUT = F"""\
<h1>{PROGRAM_NAME}</h1>
Version {VERSION}
<p>
This is my git frontend.<br>There are many like it but this one is mine.
</p>
"""

monoFont = QFontDatabase.systemFont(QFontDatabase.FixedFont)


statusIcons = {}
for status in "ACDMRTUX":
    statusIcons[status] = QIcon(F"icons/status_{status.lower()}.svg")


appSettings = QSettings('GitFourchette', 'GitFourchette')

SK_LAST_OPEN = "last_open"


graphViewTimeFormat = appSettings.value("GraphView/TimeFormat", "%d-%m-%y %H:%M")
appSettings.setValue("GraphView/TimeFormat", graphViewTimeFormat)

