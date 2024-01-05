from gitfourchette.porcelain import *
from gitfourchette.qt import *
from gitfourchette.toolbox import *
from gitfourchette.trtables import TrTables
from gitfourchette.forms.ui_signatureform import Ui_SignatureForm


class SignatureForm(QWidget):
    signatureChanged = Signal()

    @staticmethod
    def validateInput(item: str) -> str:
        try:
            validate_signature_item(item)
            return ""
        except NameValidationError as exc:
            return TrTables.refNameValidation(exc.code)

    def __init__(self, parent):
        super().__init__(parent)
        self.ui = Ui_SignatureForm()
        self.ui.setupUi(self)

        self.ui.nameEdit.textChanged.connect(self.signatureChanged)
        self.ui.emailEdit.textChanged.connect(self.signatureChanged)
        self.ui.timeEdit.timeChanged.connect(self.signatureChanged)
        self.ui.nowButton.clicked.connect(self.setDateTimeNow)

    def setSignature(self, signature: Signature):
        qdt: QDateTime = QDateTime.fromSecsSinceEpoch(signature.time, Qt.TimeSpec.OffsetFromUTC, signature.offset * 60)
        self.ui.nameEdit.setText(signature.name)
        self.ui.emailEdit.setText(signature.email)
        self.ui.timeEdit.setDateTime(qdt)

    def setDateTimeNow(self):
        now = QDateTime.currentDateTime()
        self.ui.timeEdit.setDateTime(now)

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
