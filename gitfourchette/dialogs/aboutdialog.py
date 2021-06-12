from allqt import *
from settings import PROGRAM_NAME, VERSION
import pygit2
import sys


def showAboutDialog(parent: QWidget):
    aboutText = F"""\
<span style="font-size: xx-large">{PROGRAM_NAME}</span>
<p>
The no-frills git GUI for Linux.
<br><a href="https://github.com/jorio/gitfourchette">https://github.com/jorio/gitfourchette</a>
</p>
<p>
&copy; 2020-2021 Iliyas Jorio
</p>
<pre><small
>{PROGRAM_NAME} {VERSION}
libgit2       {pygit2.LIBGIT2_VERSION}
pygit2        {pygit2.__version__}
Qt            {qtVersion}
PySide        {qtBindingVersion}
Python        {'.'.join(str(i) for i in sys.version_info)}</small></pre>

Have fun!"""

    QMessageBox.about(parent, F"About {PROGRAM_NAME}", aboutText)
