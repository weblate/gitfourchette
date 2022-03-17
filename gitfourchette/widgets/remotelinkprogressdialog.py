from gitfourchette.qt import *
from gitfourchette.remotelink import RemoteLink
from gitfourchette import settings


class RemoteLinkProgressDialog(QProgressDialog):
    def __init__(self, parent):
        super().__init__("Connecting to remote...\n", "Abort", 0, 0, parent)

        progress = self

        progress.setWindowTitle("Remote operation")
        progress.setMinimumWidth(8 * progress.fontMetrics().horizontalAdvance("WWWWW"))
        progress.setWindowFlags(Qt.Dialog)
        progress.setAttribute(Qt.WA_DeleteOnClose)
        if not settings.TEST_MODE:
            progress.show()

        self.remoteLink = RemoteLink()
        self.remoteLink.signals.message.connect(self.setLabelText)
        self.remoteLink.signals.progress.connect(self.onRemoteLinkProgress)

    def onRemoteLinkProgress(self, hi, cur):
        self.setMaximum(hi)
        self.setValue(cur)
