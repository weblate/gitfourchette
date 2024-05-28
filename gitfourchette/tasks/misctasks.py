import logging
from contextlib import suppress

from gitfourchette import settings
from gitfourchette.forms.reposettingsdialog import RepoSettingsDialog
from gitfourchette.qt import *
from gitfourchette.tasks.repotask import RepoTask, TaskEffects

logger = logging.getLogger(__name__)


class EditRepoSettings(RepoTask):
    def effects(self):
        return TaskEffects.Nothing

    def flow(self):
        dlg = RepoSettingsDialog(self.repo, self.parentWidget())
        dlg.setWindowModality(Qt.WindowModality.WindowModal)
        yield from self.flowDialog(dlg)

        localName, localEmail = dlg.localIdentity()
        nickname = dlg.ui.nicknameEdit.text()
        dlg.deleteLater()

        configObject = self.repo.config
        for key, value in [("user.name", localName), ("user.email", localEmail)]:
            if value:
                configObject[key] = value
            else:
                with suppress(KeyError):
                    del configObject[key]
        self.repo.scrub_empty_config_section("user")

        if nickname != settings.history.getRepoNickname(self.repo.workdir, strict=True):
            settings.history.setRepoNickname(self.repo.workdir, nickname)
            settings.history.setDirty()
            self.rw.nameChange.emit()
