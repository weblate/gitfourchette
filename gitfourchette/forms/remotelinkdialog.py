# -----------------------------------------------------------------------------
# Copyright (C) 2024 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

from gitfourchette.forms.ui_remotelinkdialog import Ui_RemoteLinkDialog
from gitfourchette.qt import *
from gitfourchette.remotelink import RemoteLink
from gitfourchette.toolbox import *


class RemoteLinkDialog(QDialog):
    def __init__(self, title: str, parent: QWidget):
        super().__init__(parent)
        title = title or self.tr("Remote operation")

        self.ui = Ui_RemoteLinkDialog()
        self.ui.setupUi(self)

        self.setMinimumWidth(self.fontMetrics().horizontalAdvance("W" * 40))
        self.setWindowTitle(title)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.CustomizeWindowHint | Qt.WindowType.WindowTitleHint)  # hide close button
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        tweakWidgetFont(self.ui.remoteLabel, 88)
        self.setStatusText(title)
        self.beginRemote("", "...")

        self.resize(self.width(), 1)
        self.show()

        self.remoteLink = RemoteLink(self)
        self.remoteLink.message.connect(self.setStatusText)
        self.remoteLink.progress.connect(self.onRemoteLinkProgress)
        self.remoteLink.beginRemote.connect(self.beginRemote)

    @property
    def abortButton(self) -> QPushButton:
        return self.ui.buttonBox.button(QDialogButtonBox.StandardButton.Abort)

    def beginRemote(self, name: str, url: str):
        if name:
            self.ui.remoteLabel.setText(f"<b>{escape(name)}:</b> {escape(url)}")
            self.setStatusText(self.tr("Connecting to {0}...").format(lquo(name)))
        else:
            self.ui.remoteLabel.setText(escamp(url))
            self.setStatusText(self.tr("Connecting..."))

    def onRemoteLinkProgress(self, value: int, maximum: int):
        self.ui.progressBar.setMaximum(maximum)
        self.ui.progressBar.setValue(value)

    def setStatusText(self, text: str):
        # Init dialog with room to fit 2 lines vertically,
        # so that it doesn't jump around when updating label text
        if "\n" not in text:
            text += "\n"
        self.ui.statusLabel.setText(text)

    def reject(self):  # bound to abort button
        if not self.remoteLink.isBusy():  # allow close()
            super().reject()
            return

        if self.remoteLink.isAborting():
            QApplication.beep()
            return

        self.remoteLink.raiseAbortFlag()
        self.abortButton.setEnabled(False)
        self.abortButton.setText(self.tr("Aborting"))
        self.onRemoteLinkProgress(0, 0)
