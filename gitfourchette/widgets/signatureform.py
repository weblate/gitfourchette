from gitfourchette.qt import *
from gitfourchette.widgets.ui_signatureform import Ui_SignatureForm
from pygit2 import Signature


class SignatureForm(QWidget):
    signatureChanged = Signal()

    def __init__(self, parent):
        super().__init__(parent)
        self.ui = Ui_SignatureForm()
        self.ui.setupUi(self)

        self.ui.nameEdit.textChanged.connect(self.signatureChanged)
        self.ui.emailEdit.textChanged.connect(self.signatureChanged)
        self.ui.timeEdit.timeChanged.connect(self.signatureChanged)

    def setSignature(self, signature: Signature):
        qdt: QDateTime = QDateTime.fromSecsSinceEpoch(signature.time, Qt.TimeSpec.OffsetFromUTC, signature.offset * 60)
        self.ui.nameEdit.setText(signature.name)
        self.ui.emailEdit.setText(signature.email)
        self.ui.timeEdit.setDateTime(qdt)

    def isValid(self) -> bool:
        # pygit2 will raise GitError if either the author or the email is empty or whitespace-only
        hasAuthor = bool(self.ui.nameEdit.text().strip())
        hasEmail = bool(self.ui.emailEdit.text().strip())
        return hasAuthor and hasEmail

    def getSignature(self) -> Signature:
        qdt = self.ui.timeEdit.dateTime()
        return Signature(
            name=self.ui.nameEdit.text(),
            email=self.ui.emailEdit.text(),
            time=qdt.toSecsSinceEpoch(),
            offset=qdt.offsetFromUtc()//60
        )
