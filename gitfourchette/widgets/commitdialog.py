from gitfourchette.qt import *
from gitfourchette.toolbox import *
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

        self.validator = ValidatorMultiplexer(self)
        self.validator.setGatedWidgets(self.ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok))
        self.validator.connectInput(self.ui.summaryEditor, self.hasNonBlankSummary, showWarning=False)
        self.ui.authorSignature.installValidator(self.validator)

        self.ui.summaryEditor.textChanged.connect(self.updateCounterLabel)
        self.ui.revealAuthor.stateChanged.connect(self.validator.run)

        split = initialText.split('\n', 1)
        if len(split) >= 1:
            self.ui.summaryEditor.setText(split[0].strip())
        if len(split) >= 2:
            self.ui.descriptionEditor.setPlainText(split[1].strip())

        self.ui.revealAuthor.setChecked(False)
        self.ui.authorGroupBox.setVisible(False)

        self.updateCounterLabel()
        self.validator.run()

    def updateCounterLabel(self):
        text = self.ui.summaryEditor.text()
        self.ui.counterLabel.setText(str(len(text)))

    def hasNonBlankSummary(self, text):
        if bool(text.strip()):
            return ""
        else:
            return self.tr("Cannot be empty.")

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

