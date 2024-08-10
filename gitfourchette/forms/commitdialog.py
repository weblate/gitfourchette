from gitfourchette.forms.signatureform import SignatureForm, SignatureOverride
from gitfourchette.porcelain import *
from gitfourchette.qt import *
from gitfourchette.toolbox import *
from gitfourchette.forms.ui_commitdialog import Ui_CommitDialog

INFO_ICON_SIZE = 16


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
            repositoryState: RepositoryState,
            parent: QWidget):
        super().__init__(parent)

        self.originalAuthorSignature = authorSignature
        self.originalCommitterSignature = committerSignature

        self.ui = Ui_CommitDialog()
        self.ui.setupUi(self)

        self.ui.signatureButton.setIcon(stockIcon("view-visible"))

        self.ui.signature.setSignature(authorSignature)
        self.ui.signature.signatureChanged.connect(self.refreshSignaturePreview)

        # Make summary text edit font larger
        tweakWidgetFont(self.ui.summaryEditor, 130)

        if amendingCommitHash:
            prompt = self.tr("Amend commit message")
            buttonCaption = self.tr("A&mend")
            self.setWindowTitle(self.tr("Amend Commit {0}").format(amendingCommitHash))
        else:
            prompt = self.tr("Enter commit summary")
            buttonCaption = self.tr("Co&mmit")
            self.setWindowTitle(self.tr("Commit"))

        warning = ""
        if repositoryState == RepositoryState.MERGE:
            warning = self.tr("This commit will conclude the merge.")
        elif repositoryState == RepositoryState.CHERRYPICK:
            warning = self.tr("This commit will conclude the cherry-pick.")
        elif repositoryState == RepositoryState.REVERT:
            warning = self.tr("This commit will conclude the revert.")
        elif amendingCommitHash:
            warning = self.tr("You are amending commit {0}.").format(lquo(amendingCommitHash))
        elif detachedHead:
            warning = self.tr("<b>Detached HEAD</b> – You are not in any branch! "
                              "You should create a branch to keep track of your commit.")

        self.ui.infoBox.setVisible(bool(warning))
        self.ui.infoText.setText(warning)
        self.ui.infoIcon.setPixmap(stockIcon("SP_MessageBoxInformation").pixmap(INFO_ICON_SIZE))
        self.ui.infoIcon.setMaximumWidth(INFO_ICON_SIZE)

        self.acceptButton.setText(buttonCaption)
        self.ui.summaryEditor.setPlaceholderText(prompt)

        self.ui.counterLabel.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.ui.counterLabel.setMinimumWidth(self.ui.counterLabel.fontMetrics().horizontalAdvance('000'))
        self.ui.counterLabel.setMaximumWidth(self.ui.counterLabel.minimumWidth())

        self.validator = ValidatorMultiplexer(self)
        self.validator.setGatedWidgets(self.ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok))
        self.validator.connectInput(self.ui.summaryEditor, self.hasNonBlankSummary, showError=False)
        self.ui.signature.installValidator(self.validator)

        self.ui.summaryEditor.textChanged.connect(self.updateCounterLabel)
        self.ui.revealSignature.stateChanged.connect(self.validator.run)
        self.ui.revealSignature.stateChanged.connect(lambda: self.refreshSignaturePreview())

        split = initialText.split('\n', 1)
        if len(split) >= 1:
            self.ui.summaryEditor.setText(split[0].strip())
        if len(split) >= 2:
            self.ui.descriptionEditor.setPlainText(split[1].strip())

        self.ui.revealSignature.setChecked(False)
        self.ui.signatureBox.setVisible(False)

        self.updateCounterLabel()
        self.validator.run()
        self.refreshSignaturePreview()

        # Focus on summary editor before showing
        self.ui.summaryEditor.setFocus()

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

    def getOverriddenSignatureKind(self):
        if not self.ui.revealSignature.isChecked():
            return SignatureOverride.Nothing
        return self.ui.signature.replaceWhat()

    def getOverriddenAuthorSignature(self):
        if self.getOverriddenSignatureKind() in [SignatureOverride.Author, SignatureOverride.Both]:
            return self.ui.signature.getSignature()
        else:
            return None

    def getOverriddenCommitterSignature(self):
        if self.getOverriddenSignatureKind() in [SignatureOverride.Committer, SignatureOverride.Both]:
            return self.ui.signature.getSignature()
        else:
            return None

    def refreshSignaturePreview(self):
        def formatSignatureForToolTip(sig: Signature):
            if sig is None:
                return "???"
            qdt = QDateTime.fromSecsSinceEpoch(sig.time, Qt.TimeSpec.OffsetFromUTC, sig.offset * 60)
            return F"{escape(sig.name)} &lt;{escape(sig.email)}&gt;<br>" \
                + "<small>" + escape(QLocale().toString(qdt, QLocale.FormatType.LongFormat)) + "</small>"

        try:
            author = self.getOverriddenAuthorSignature() or self.originalAuthorSignature
        except ValueError:
            author = None

        try:
            committer = self.getOverriddenCommitterSignature() or self.originalCommitterSignature
        except ValueError:
            committer = None

        muted = mutedToolTipColorHex()
        tt = "<p style='white-space: pre'>"
        # tt += self.tr("The commit will be saved with the following signatures:") + "\n\n"

        tt += f"<span style='color: {muted}'>" + self.tr("Authored by:") + "</span> "
        tt += formatSignatureForToolTip(author)
        if not signatures_equalish(author, self.originalAuthorSignature):
            tt += f"\n<span style='font-weight: bold;'>" + self.tr("(overridden manually)") + "</span>"

        tt += f"\n\n<span style='color: {muted}'>" + self.tr("Committed by:") + "</span> "
        tt += formatSignatureForToolTip(committer)
        if not signatures_equalish(committer, self.originalCommitterSignature):
            tt += f"\n<span style='font-weight: bold;'>" + self.tr("(overridden manually)") + "</span>"

        self.ui.signatureButton.setToolTip(tt)
        self.ui.revealSignature.setToolTip(tt)

