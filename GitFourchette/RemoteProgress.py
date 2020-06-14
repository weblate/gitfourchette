import git
from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *


def progressOpcodeToString(op_code):
    m = op_code & git.RemoteProgress.OP_MASK
    if m == git.RemoteProgress.COUNTING:
        return "Counting"
    elif m == git.RemoteProgress.COMPRESSING:
        return "Compressing"
    elif m == git.RemoteProgress.WRITING:
        return "Writing"
    elif m == git.RemoteProgress.RECEIVING:
        return "Receiving"
    elif m == git.RemoteProgress.RESOLVING:
        return "Resolving"
    elif m == git.RemoteProgress.FINDING_SOURCES:
        return "Finding Sources"
    elif m == git.RemoteProgress.CHECKING_OUT:
        return "Checking Out"
    else:
        return "Unknown Progress Opcode"


class RemoteProgress(git.RemoteProgress):
    def __init__(self, parent, title):
        super(__class__, self).__init__()
        self.dlg = QProgressDialog("Reticulating Splines...", "Abort", 0, 0, parent)
        self.dlg.setAttribute(Qt.WA_DeleteOnClose)  # avoid leaking the dialog
        self.dlg.setWindowModality(Qt.WindowModal)
        self.dlg.setWindowTitle(title)
        self.dlg.setWindowFlags(Qt.Dialog | Qt.Popup)
        self.dlg.setMinimumWidth(2 * self.dlg.fontMetrics().width("000,000,000 commits loaded."))
        self.dlg.show()
        self.dlg.repaint()
        QCoreApplication.processEvents()
        QCoreApplication.processEvents()

    def update(self, op_code, cur_count, max_count=None, message=''):
        cur_count = int(cur_count)
        max_count = int(max_count)
        op = progressOpcodeToString(op_code)
        self.dlg.setLabelText(F"{op}... {cur_count} of {max_count}\n{message}")
        self.dlg.repaint()
        QCoreApplication.processEvents()
        print(F"Update: {op_code} {op} | {cur_count} | {max_count} | {message}")
