from allqt import *
from widgets.ui_signatureform import Ui_SignatureForm
from pygit2 import Signature


class SignatureForm(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.ui = Ui_SignatureForm()
        self.ui.setupUi(self)

    def setSignature(self, signature: Signature):
        qdt: QDateTime = QDateTime.fromSecsSinceEpoch(signature.time, Qt.TimeSpec.OffsetFromUTC, signature.offset * 60)
        self.ui.nameEdit.setText(signature.name)
        self.ui.emailEdit.setText(signature.email)
        self.ui.timeEdit.setDateTime(qdt)

    def getSignature(self) -> Signature:
        qdt = self.ui.timeEdit.dateTime()
        return Signature(
            name=self.ui.nameEdit.text(),
            email=self.ui.emailEdit.text(),
            time=QDateTime.toTime_t(qdt),
            offset=qdt.offsetFromUtc()//60
        )
