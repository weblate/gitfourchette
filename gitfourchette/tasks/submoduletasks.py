"""
Submodule management tasks.
"""

from gitfourchette.forms.brandeddialog import convertToBrandedDialog
from gitfourchette.porcelain import *
from gitfourchette.qt import *
from gitfourchette.tasks.repotask import AbortTask, RepoTask, TaskEffects
from gitfourchette.toolbox import *
from gitfourchette.forms.ui_absorbsubmodule import Ui_AbsorbSubmodule
from pathlib import Path


class AbsorbSubmodule(RepoTask):
    def effects(self) -> TaskEffects:
        return TaskEffects.Workdir | TaskEffects.Refs  # we don't have TaskEffects.Submodules so .Refs is the next best thing

    def flow(self, path: str):
        thisWD = Path(self.repo.workdir)
        thisName = thisWD.name
        subWD = Path(thisWD / path)
        subName = subWD.name
        subRemotes = {}
        subIsBare = False

        with RepoContext(thisWD / subWD) as subRepo:
            subIsBare = subRepo.is_bare
            for remote in subRepo.remotes:
                subRemotes[remote.name] = remote.url

        if subIsBare:
            message = paragraphs(
                self.tr("“{0}” is a bare repository.").format(subName),
                self.tr("This operation does not support bare repositories."))
            raise AbortTask(message)

        if not subRemotes:
            message = paragraphs(
                self.tr("“{0}” has no remotes.").format(subName),
                self.tr("Please open “{0}” and add a remote to it before absorbing it as a submodule of “{1}”.").format(subName, thisName))
            raise AbortTask(message)

        dlg = QDialog(self.parentWidget())

        qcb = QComboBoxWithPreview(dlg)
        for k, v in subRemotes.items():
            qcb.addItemWithPreview(k, v, v)

        ui = Ui_AbsorbSubmodule()
        ui.setupUi(dlg)
        dlg.ui = ui  # for easier access in unit testing
        dlg.setWindowTitle(self.name())
        formatWidgetText(ui.label1, sub=escape(subName), super=escape(thisName))
        formatWidgetText(ui.label2, sub=escape(subName), super=escape(thisName))
        ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok).setText(self.tr("Absorb submodule"))

        ui.comboBox.parent().layout().addWidget(qcb)
        ui.comboBox.deleteLater()

        convertToBrandedDialog(dlg)
        setWindowModal(dlg)
        dlg.setMinimumWidth(512)
        # dlg.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.MinimumExpanding)
        dlg.show()
        # dlg.setMinimumHeight(dlg.height())
        dlg.setMaximumHeight(dlg.height())

        # yield from self._flowConfirm(text=prompt)
        yield from self.flowDialog(dlg)

        remoteUrl = qcb.currentData(Qt.ItemDataRole.UserRole)
        dlg.deleteLater()

        yield from self.flowEnterWorkerThread()
        subrepo = self.repo.add_inner_repo_as_submodule(str(subWD.relative_to(thisWD)), remoteUrl)
