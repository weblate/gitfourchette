from gitfourchette.forms.ui_registersubmoduledialog import Ui_RegisterSubmoduleDialog
from gitfourchette.porcelain import *
from gitfourchette.qt import *
from gitfourchette.toolbox import formatWidgetText, lquoe


class RegisterSubmoduleDialog(QDialog):
    def __init__(
            self,
            currentName: str,
            fallbackName: str,
            superprojectName: str,
            remotes: dict[str, str],
            absorb: bool,
            parent):
        super().__init__(parent)
        ui = Ui_RegisterSubmoduleDialog()
        ui.setupUi(self)
        self.ui = ui

        for k, v in remotes.items():
            ui.remoteComboBox.addItemWithPreview(k, v, v)

        ui.nameEdit.setText(currentName)
        ui.nameEdit.setPlaceholderText(fallbackName)

        okButton = ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok)

        if absorb:
            formatWidgetText(ui.absorbExplainer, sub=lquoe(fallbackName), super=lquoe(superprojectName))
            okButton.setText(self.tr("Absorb submodule"))
            self.setWindowTitle(self.tr("Absorb submodule"))
        else:
            ui.absorbExplainer.deleteLater()
            okButton.setText(self.tr("Register submodule"))
            self.setWindowTitle(self.tr("Register submodule"))

    @property
    def remoteUrl(self) -> str:
        return self.ui.remoteComboBox.currentData(Qt.ItemDataRole.UserRole)

    @property
    def customName(self):
        return self.ui.nameEdit.text()
