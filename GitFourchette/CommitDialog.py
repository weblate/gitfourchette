from PySide6.QtCore import *
from PySide6.QtGui import *
from PySide6.QtWidgets import *


class CommitDialog(QDialog):
    def __init__(self, initialText: str, isAmend: bool, parent):
        super().__init__(parent)

        if isAmend:
            prompt = "Amend commit message"
            buttonCaption = "&Amend"
            self.setWindowTitle("Amend Commit")
        else:
            prompt = "Enter commit summary"
            buttonCaption = "&Commit"
            self.setWindowTitle("Commit")

        buttonBox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)

        acceptButton = buttonBox.button(QDialogButtonBox.Ok)
        acceptButton.setText(buttonCaption)

        layout = QVBoxLayout()

        self.summaryEditor = QLineEdit()
        summaryFont = self.summaryEditor.font()
        summaryFont.setPointSize(int(summaryFont.pointSize() * 1.25))
        self.summaryEditor.setFont(summaryFont)
        self.summaryEditor.setPlaceholderText(prompt)
        self.summaryEditor.setMinimumWidth(self.summaryEditor.fontMetrics().horizontalAdvance('M'*30))

        counterLabel = QLabel("0")
        counterLabel.setEnabled(False)
        counterLabel.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        counterLabel.setMinimumWidth(counterLabel.fontMetrics().horizontalAdvance('000'))
        counterLabel.setMaximumWidth(counterLabel.minimumWidth())

        def onSummaryChanged():
            text = self.summaryEditor.text()
            hasText = bool(text.strip())
            counterLabel.setText(str(len(text)))
            acceptButton.setEnabled(hasText)
        self.summaryEditor.textChanged.connect(onSummaryChanged)

        self.descriptionEditor = QPlainTextEdit()
        self.descriptionEditor.setPlaceholderText("Long-form description (optional)")
        self.descriptionEditor.setTabChangesFocus(True)
        self.descriptionEditor.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents)

        summaryRowLayout = QHBoxLayout()
        summaryRowLayout.setSpacing(0)
        summaryRowLayout.setContentsMargins(0, 0, 0, 0)
        summaryRowLayout.addWidget(self.summaryEditor)
        summaryRowLayout.addWidget(counterLabel)
        summaryRow = QWidget()
        summaryRow.setLayout(summaryRowLayout)

        layout.addWidget(summaryRow)
        layout.addWidget(self.descriptionEditor)
        layout.addWidget(buttonBox)

        split = initialText.split('\n', 1)
        if len(split) >= 1:
            self.summaryEditor.setText(split[0].strip())
        if len(split) >= 2:
            self.descriptionEditor.setPlainText(split[1].strip())

        onSummaryChanged()

        self.setLayout(layout)

    def hasNonBlankSummary(self):
        return bool(self.summaryEditor.text().strip())

    def getFullMessage(self):
        summary = self.summaryEditor.text()
        details = self.descriptionEditor.toPlainText()

        hasDetails = bool(details.strip())

        if not hasDetails:
            return summary

        return F"{summary}\n\n{details}"
