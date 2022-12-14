from gitfourchette.qt import *
from gitfourchette.util import stockIcon, setWindowModal
from gitfourchette.remotelink import RemoteLink
from gitfourchette import settings


class RemoteLinkProgressDialog(QProgressDialog):
    def __init__(self, parent):
        # Init dialog with room to fit 2 lines vertically, so that it doesn't jump around when updating label text
        fittingLine = "W" * 40
        fittingText = f"{fittingLine}\n{fittingLine}"

        super().__init__(fittingText, None, 0, 0, parent)

        progress = self

        self.abortButton = QPushButton(stockIcon(QStyle.StandardPixmap.SP_DialogAbortButton), self.tr("Abort"))
        progress.setCancelButton(self.abortButton)

        progress.setWindowTitle(self.tr("Remote operation"))
        progress.setMinimumWidth(progress.fontMetrics().horizontalAdvance(fittingLine))
        progress.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowTitleHint | Qt.WindowType.CustomizeWindowHint)  # hide close button
        progress.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        setWindowModal(progress)

        # By default, the cancel button emits the 'canceled' signal, which is connected to the 'cancel' slot.
        # The 'cancel' slot hides the dialog. However, we don't want to hide it immediately after the user aborts.
        progress.canceled.disconnect(progress.cancel)
        progress.canceled.connect(self.userAbort)

        if not settings.TEST_MODE:
            progress.show()

        # Set initial text after showing the dialog so it is sized correctly
        progress.setLabelText(self.tr("Connecting to remote..."))

        self.remoteLink = RemoteLink(self)
        self.remoteLink.message.connect(self.setLabelText)
        self.remoteLink.progress.connect(self.onRemoteLinkProgress)

    #def reject(self):
    #    """Called when user clicks window close button"""
    #    self.userAbort()

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
