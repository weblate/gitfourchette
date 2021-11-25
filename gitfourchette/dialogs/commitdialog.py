from allqt import *
from ui.ui_commitdialog import Ui_CommitDialog


class CommitDialog(QDialog):
    def __init__(self, initialText: str, isAmend: bool, parent):
        super().__init__(parent)

        self.ui = Ui_CommitDialog()
        self.ui.setupUi(self)

        acceptButton = self.ui.buttonBox.button(QDialogButtonBox.Ok)
        counterLabel = self.ui.counterLabel
        summaryEditor = self.ui.summaryEditor
        descriptionEditor = self.ui.descriptionEditor

        if isAmend:
            prompt = "Amend commit message"
            buttonCaption = "&Amend"
            self.setWindowTitle("Amend Commit")
        else:
            prompt = "Enter commit summary"
            buttonCaption = "&Commit"
            self.setWindowTitle("Commit")

        acceptButton.setText(buttonCaption)
        summaryEditor.setPlaceholderText(prompt)

        counterLabel.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        counterLabel.setMinimumWidth(counterLabel.fontMetrics().horizontalAdvance('000'))
        counterLabel.setMaximumWidth(counterLabel.minimumWidth())

        def onSummaryChanged():
            text = summaryEditor.text()
            hasText = bool(text.strip())
            counterLabel.setText(str(len(text)))
            acceptButton.setEnabled(hasText)
        summaryEditor.textChanged.connect(onSummaryChanged)

        split = initialText.split('\n', 1)
        if len(split) >= 1:
            summaryEditor.setText(split[0].strip())
        if len(split) >= 2:
            descriptionEditor.setPlainText(split[1].strip())

        onSummaryChanged()

    def hasNonBlankSummary(self):
        return bool(self.ui.summaryEditor.text().strip())

    def getFullMessage(self):
        summary = self.ui.summaryEditor.text()
        details = self.ui.descriptionEditor.toPlainText()

        hasDetails = bool(details.strip())

        if not hasDetails:
            return summary

        return F"{summary}\n\n{details}"
