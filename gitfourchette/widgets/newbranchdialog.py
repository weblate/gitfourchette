from gitfourchette import exttools
from gitfourchette.qt import *
from gitfourchette.toolbox import *
from gitfourchette.widgets.brandeddialog import convertToBrandedDialog
from gitfourchette.widgets.ui_newbranchdialog import Ui_NewBranchDialog


class NewBranchDialog(QDialog):
    def __init__(
            self,
            initialName: str,
            target: str,
            targetSubtitle: str,
            upstreams: list[str],
            reservedNames: list[str],
            parent=None):

        super().__init__(parent)

        self.ui = Ui_NewBranchDialog()
        self.ui.setupUi(self)

        self.ui.nameEdit.setText(initialName)

        self.acceptButton.setText(self.tr("Create branch"))

        self.ui.upstreamComboBox.addItems(upstreams)

        # hack to trickle down initial 'toggled' signal to combobox
        self.ui.upstreamCheckBox.setChecked(True)
        self.ui.upstreamCheckBox.setChecked(False)

        if not upstreams:
            self.ui.upstreamCheckBox.setChecked(False)
            self.ui.upstreamCheckBox.setVisible(False)
            self.ui.upstreamComboBox.setVisible(False)

        nameTaken = self.tr("This name is already taken by another local branch.")
        validator = ValidatorMultiplexer(self)
        validator.setGatedWidgets(self.acceptButton)
        validator.connectInput(self.ui.nameEdit, lambda name: nameValidationMessage(name, reservedNames, nameTaken))
        validator.run()

        convertToBrandedDialog(self, self.tr("New branch"),
                               self.tr("Commit at tip:") + f" {target}\n“{targetSubtitle}”")

        self.ui.nameEdit.setFocus()
        self.ui.nameEdit.selectAll()

    @property
    def acceptButton(self):
        return self.ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok)
