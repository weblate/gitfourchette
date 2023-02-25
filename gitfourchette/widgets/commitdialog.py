from gitfourchette.qt import *
from gitfourchette.util import tweakWidgetFont
from gitfourchette.widgets.ui_commitdialog import Ui_CommitDialog
from pygit2 import Signature


class CommitDialog(QDialog):
    @property
    def acceptButton(self) -> QPushButton:
        return self.ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok)

    def __init__(
            self,
            initialText: str,
            authorSignature: Signature,
            committerSignature: Signature,
            amendingCommitHash: str,
            detachedHead: bool,
            parent):
        super().__init__(parent)

        self.ui = Ui_CommitDialog()
        self.ui.setupUi(self)

        # Make summary text edit font larger
        tweakWidgetFont(self.ui.summaryEditor, 150)

        if amendingCommitHash:
            prompt = self.tr("Amend commit message")
            buttonCaption = self.tr("&Amend")
            self.setWindowTitle(self.tr("Amend Commit {0}").format(amendingCommitHash))
        else:
            prompt = self.tr("Enter commit summary")
            buttonCaption = self.tr("&Commit")
            self.setWindowTitle(self.tr("Commit"))

        self.ui.detachedHeadWarning.setVisible(detachedHead)

        self.ui.authorSignature.setSignature(authorSignature)

        self.acceptButton.setText(buttonCaption)
        self.ui.summaryEditor.setPlaceholderText(prompt)

        self.ui.counterLabel.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.ui.counterLabel.setMinimumWidth(self.ui.counterLabel.fontMetrics().horizontalAdvance('000'))
        self.ui.counterLabel.setMaximumWidth(self.ui.counterLabel.minimumWidth())

        self.ui.summaryEditor.textChanged.connect(self.updateCounterLabel)
        self.ui.summaryEditor.textChanged.connect(self.updateAcceptButton)
        self.ui.revealAuthor.stateChanged.connect(self.updateAcceptButton)
        self.ui.authorSignature.signatureChanged.connect(self.updateAcceptButton)

        split = initialText.split('\n', 1)
        if len(split) >= 1:
            self.ui.summaryEditor.setText(split[0].strip())
        if len(split) >= 2:
            self.ui.descriptionEditor.setPlainText(split[1].strip())

        self.updateCounterLabel()
        self.updateAcceptButton()

        self.ui.revealAuthor.setChecked(False)
        self.ui.authorGroupBox.setVisible(False)

    def updateCounterLabel(self):
        text = self.ui.summaryEditor.text()
        self.ui.counterLabel.setText(str(len(text)))

    def updateAcceptButton(self):
        self.acceptButton.setEnabled(self.canProceed())

    def canProceed(self):
        text = self.ui.summaryEditor.text()
        hasAnyText = bool(text.strip())
        signatureValid = not self.ui.revealAuthor.isChecked() or self.ui.authorSignature.isValid()
        return hasAnyText and signatureValid

    def hasNonBlankSummary(self):
        return bool(self.ui.summaryEditor.text().strip())

    def getFullMessage(self):
        summary = self.ui.summaryEditor.text()
        details = self.ui.descriptionEditor.toPlainText()

        hasDetails = bool(details.strip())

        if not hasDetails:
            return summary

        return F"{summary}\n\n{details}"

    def getOverriddenAuthorSignature(self):
        if self.ui.revealAuthor.isChecked():
            return self.ui.authorSignature.getSignature()
        else:
            return None

    def getOverriddenCommitterSignature(self):
        return self.getOverriddenAuthorSignature()

