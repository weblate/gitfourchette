from gitfourchette import porcelain
from gitfourchette.qt import *
from gitfourchette.toolbox import *
from gitfourchette.trtables import translateNameValidationCode
from gitfourchette.forms.ui_signatureform import Ui_SignatureForm
from pygit2 import Signature


class SignatureForm(QWidget):
    signatureChanged = Signal()

    @staticmethod
    def validateInput(item: str) -> str:
        try:
            porcelain.validateSignatureItem(item)
            return ""
        except porcelain.NameValidationError as exc:
            return translateNameValidationCode(exc.code)

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

    def installValidator(self, validator: ValidatorMultiplexer):
        validator.connectInput(self.ui.nameEdit, SignatureForm.validateInput)
        validator.connectInput(self.ui.emailEdit, SignatureForm.validateInput)

    def getSignature(self) -> Signature:
        qdt = self.ui.timeEdit.dateTime()
        return Signature(
            name=self.ui.nameEdit.text(),
            email=self.ui.emailEdit.text(),
            time=qdt.toSecsSinceEpoch(),
            offset=qdt.offsetFromUtc()//60
        )
