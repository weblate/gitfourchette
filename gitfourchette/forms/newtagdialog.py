from gitfourchette.qt import *
from gitfourchette.toolbox import *
from gitfourchette.forms.brandeddialog import convertToBrandedDialog
from gitfourchette.forms.ui_newtagdialog import Ui_NewTagDialog


class NewTagDialog(QDialog):
    def __init__(
            self,
            target: str,
            targetSubtitle: str,
            reservedNames: list[str],
            remotes: list[str],
            parent=None):

        super().__init__(parent)

        self.ui = Ui_NewTagDialog()
        self.ui.setupUi(self)

        self.acceptButton.setText(self.tr("&Create"))
        self.ui.pushCheckBox.toggled.connect(
            lambda push: self.acceptButton.setText(self.tr("&Create") if not push else self.tr("&Create && Push")))

        assert 1 == self.ui.remotesComboBox.count()
        self.ui.remotesComboBox.setItemData(0, "*")  # asterisk = all remotes
        self.ui.remotesComboBox.insertSeparator(1)
        for remote in remotes:
            self.ui.remotesComboBox.addItem(remote, userData=remote)

        nameTaken = self.tr("This name is already taken by another tag.")
        validator = ValidatorMultiplexer(self)
        validator.setGatedWidgets(self.acceptButton)
        validator.connectInput(self.ui.nameEdit, lambda name: nameValidationMessage(name, reservedNames, nameTaken))
        validator.run(silenceEmptyWarnings=True)

        convertToBrandedDialog(self, self.tr("New tag on commit {0}").format(tquo(target)),
                               tquo(targetSubtitle))

        self.resize(max(512, self.width()), self.height())

        # Prime enabled state
        self.ui.pushCheckBox.click()
        self.ui.pushCheckBox.click()

        if not remotes:
            self.ui.pushCheckBox.setChecked(False)
            self.ui.pushCheckBox.setEnabled(False)
            self.ui.remotesComboBox.setItemText(0, self.tr("No remotes"))

    @property
    def acceptButton(self):
        return self.ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok)
