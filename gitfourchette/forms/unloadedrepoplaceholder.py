# -----------------------------------------------------------------------------
# Copyright (C) 2024 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

from gitfourchette.qt import *
from gitfourchette.toolbox import *
from gitfourchette.forms.ui_unloadedrepoplaceholder import Ui_UnloadedRepoPlaceholder


class UnloadedRepoPlaceholder(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ui = Ui_UnloadedRepoPlaceholder()
        self.ui.setupUi(self)
        tweakWidgetFont(self.ui.nameLabel, bold=True)
