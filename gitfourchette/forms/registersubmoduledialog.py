from gitfourchette.forms.ui_registersubmoduledialog import Ui_RegisterSubmoduleDialog
from gitfourchette.qt import *
from gitfourchette.toolbox import *


class RegisterSubmoduleDialog(QDialog):
    def __init__(
            self,
            workdirPath: str,
            superprojectName: str,
            remotes: dict[str, str],
            absorb: bool,
            reservedNames: list[str],
            parent):
        super().__init__(parent)
        ui = Ui_RegisterSubmoduleDialog()
        ui.setupUi(self)
        self.ui = ui
        self.reservedNames = reservedNames

        for k, v in remotes.items():
            ui.remoteComboBox.addItemWithPreview(k, v, v)

        ui.pathValue.setText(workdirPath)
        ui.nameEdit.setText(workdirPath)
        ui.nameEdit.addAction(stockIcon("git-submodule"), QLineEdit.ActionPosition.LeadingPosition)
        self.resetNameAction = ui.nameEdit.addAction(stockIcon("SP_LineEditClearButton"), QLineEdit.ActionPosition.TrailingPosition)
        self.resetNameAction.setVisible(False)
        self.resetNameAction.setToolTip(self.tr("Reset to default name"))
        self.resetNameAction.triggered.connect(lambda: ui.nameEdit.setText(workdirPath))
        ui.nameEdit.textChanged.connect(lambda name: self.resetNameAction.setVisible(name != workdirPath))

        if absorb:
            formatWidgetText(ui.absorbExplainer, sub=lquoe(workdirPath), super=lquoe(superprojectName))
            self.okButton.setText(self.tr("Absorb submodule"))
            self.setWindowTitle(self.tr("Absorb submodule"))
        else:
            ui.absorbExplainer.hide()
            self.okButton.setText(self.tr("Register submodule"))
            self.setWindowTitle(self.tr("Register submodule"))

        validator = ValidatorMultiplexer(self)
        validator.setGatedWidgets(self.okButton)
        validator.connectInput(self.ui.nameEdit, self.validateSubmoduleName)
        validator.run()

    @property
    def remoteUrl(self) -> str:
        return self.ui.remoteComboBox.currentData(Qt.ItemDataRole.UserRole)

    @property
    def customName(self):
        return self.ui.nameEdit.text()

    @property
    def okButton(self):
        return self.ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok)

    def validateSubmoduleName(self, name: str):
        if not name.strip():
            return translate("NameValidationError", "Cannot be empty.")
        elif name in self.reservedNames:
            return translate("NameValidationError", "This name is already taken by another submodule.")
        else:
            return ""
