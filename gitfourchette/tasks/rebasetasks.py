# -----------------------------------------------------------------------------
# Copyright (C) 2026 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

import logging
import shlex

import gitfourchette.rebase.sequenceeditor
from gitfourchette.exttools.toolcommands import ToolCommands
from gitfourchette.porcelain import Oid
from gitfourchette.tasks import TaskPrereqs
from gitfourchette.tasks.repotask import RepoTask

logger = logging.getLogger(__name__)


class InteractiveRebase(RepoTask):
    def prereqs(self):
        # TODO: need clean workdir, too
        return TaskPrereqs.NoConflicts | TaskPrereqs.NoUnborn | TaskPrereqs.NoCherrypick

    def flow(self, rootCommit: Oid):
        sequenceEditorTokens = ToolCommands.spawnNewInstance(gitfourchette.rebase.sequenceeditor.__name__)
        sequenceEditorCommand = shlex.join(sequenceEditorTokens)
        yield from self.flowCallGit(
            "-c", "core.abbrev=no",
            "rebase", "-i", str(rootCommit),
            # "--keep-base",
            env={"GIT_SEQUENCE_EDITOR": sequenceEditorCommand},
        )
