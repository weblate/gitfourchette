from gitfourchette.forms.newtagdialog import populateRemoteComboBox
from gitfourchette.qt import *
from gitfourchette.toolbox import *
from gitfourchette.forms.brandeddialog import convertToBrandedDialog
from gitfourchette.forms.ui_deletetagdialog import Ui_DeleteTagDialog


class DeleteTagDialog(QDialog):
    def __init__(
            self,
            tagName: str,
            target: str,
            targetSubtitle: str,
            remotes: list[str],
            parent=None):

        super().__init__(parent)

        self.ui = Ui_DeleteTagDialog()
        self.ui.setupUi(self)

        formatWidgetText(self.ui.label, bquo(tagName))

        okButton = self.ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok)
        okButton.setIcon(stockIcon("SP_DialogDiscardButton"))
        okCaptions = [self.tr("&Delete Locally"), self.tr("&Delete Locally && Remotely")]
        self.ui.pushCheckBox.toggled.connect(lambda push: okButton.setText(okCaptions[push]))

        populateRemoteComboBox(self.ui.remoteComboBox, remotes)

        # Prime enabled state
        self.ui.pushCheckBox.click()
        self.ui.pushCheckBox.click()
        if not remotes:
            self.ui.pushCheckBox.setChecked(False)
            self.ui.pushCheckBox.setEnabled(False)

        convertToBrandedDialog(
            self,
            self.tr("Delete tag {0}").format(tquo(tagName)),
            self.tr("Tagged commit: {0}").format(target) + " – " + tquo(targetSubtitle))

        self.resize(max(512, self.width()), self.height())
