from gitfourchette.qt import *
from gitfourchette.remotelink import RemoteLink
from gitfourchette.toolbox import *


class RemoteLinkProgressDialog(QProgressDialog):
    def __init__(self, title: str, parent: QWidget):
        super().__init__("", None, 0, 0, parent)

        # Init dialog with room to fit 2 lines vertically, so that it doesn't jump around when updating label text
        self.setLabelText(self.tr("Connecting to remote...") + "\n")

        self.abortButton = QPushButton(stockIcon("SP_DialogAbortButton"), self.tr("Abort"))
        self.setCancelButton(self.abortButton)

        self.setWindowTitle(title or self.tr("Remote operation"))
        self.setMinimumWidth(self.fontMetrics().horizontalAdvance("W" * 40))
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.CustomizeWindowHint | Qt.WindowType.WindowTitleHint)  # hide close button
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowModality(Qt.WindowModality.WindowModal)

        # By default, the cancel button emits the 'canceled' signal, which is connected to the 'cancel' slot.
        # The 'cancel' slot hides the dialog. However, we don't want to hide it immediately after the user aborts.
        self.canceled.disconnect(self.cancel)
        self.canceled.connect(self.userAbort)

        self.show()

        self.remoteLink = RemoteLink(self)
        self.remoteLink.message.connect(self.setLabelText)
        self.remoteLink.progress.connect(self.onRemoteLinkProgress)

    def userAbort(self):
        self.remoteLink.raiseAbortFlag()
        self.abortButton.setEnabled(False)

    def onRemoteLinkProgress(self, value: int, maximum: int):
        self.setMaximum(maximum)
        self.setValue(value)

    def close(self):
        # We're being closed by user code on completion, don't raise abort flag
        self.canceled.disconnect(self.userAbort)
        super().close()
