import contextlib

from gitfourchette import log
from gitfourchette import settings
from gitfourchette.forms.openrepoprogress import OpenRepoProgress
from gitfourchette.graph import Graph, BatchRow
from gitfourchette.graphmarkers import ForeignCommitSolver
from gitfourchette.diffview.diffdocument import DiffDocument
from gitfourchette.diffview.specialdiff import (ShouldDisplayPatchAsImageDiff, SpecialDiffError, DiffImagePair,
                                                DiffConflict)
from gitfourchette.nav import NavLocator, NavFlags, NavContext
from gitfourchette.porcelain import *
from gitfourchette.qt import *
from gitfourchette.tasks.repotask import RepoTask, TaskEffects
from gitfourchette.toolbox import *

TAG = "LoadTasks"


class PrimeRepo(RepoTask):
    progressRange = Signal(int, int)
    progressValue = Signal(int)
    progressMessage = Signal(str)
    progressAbortable = Signal(bool)

    def _onAbortButtonClicked(self):
        self._wantAbort = True

    def flow(self, path: str):
        from gitfourchette.repowidget import RepoWidget
        from gitfourchette.repostate import RepoState, UC_FAKEID, KF_INTERVAL, PROGRESS_INTERVAL
        from gitfourchette.tasks.jumptasks import Jump

        assert path

        rw = self.rw
        assert isinstance(rw, RepoWidget)

        progressWidget = OpenRepoProgress(rw)
        rw.setPlaceholderWidget(progressWidget)

        self._wantAbort = False
        self.progressRange.connect(progressWidget.ui.progressBar.setRange)
        self.progressValue.connect(progressWidget.ui.progressBar.setValue)
        self.progressMessage.connect(progressWidget.ui.label.setText)
        self.progressAbortable.connect(progressWidget.ui.abortButton.setEnabled)
        progressWidget.ui.abortButton.clicked.connect(self._onAbortButtonClicked)
        progressWidget.ui.abortButton.setEnabled(False)

        # Create the repo
        repo = Repo(path, GIT_REPOSITORY_OPEN_NO_SEARCH)
        self.setRepo(repo)  # required to execute subtasks later

        if repo.is_shallow:
            libgit2_version_at_least("1.7.0", feature_name="Shallow clone support")

        if repo.is_bare:
            raise NotImplementedError(self.tr("Sorry, {app} doesn’t support bare repositories.").format(app=qAppName()))

        self.progressMessage.emit(self.tr("Opening “{0}”...").format(settings.history.getRepoNickname(path)))

        # Create repo state
        state = RepoState(rw, repo)

        # ---------------------------------------------------------------------
        # EXIT UI THREAD
        # ---------------------------------------------------------------------
        yield from self.flowEnterWorkerThread()

        # Prime the walker (this might take a while)
        walker = state.initializeWalker(state.refCache.values())

        state.updateActiveCommitOid()

        commitSequence: list[Commit | None] = []

        # Retrieve the number of commits that we loaded last time we opened this repo
        # so we can estimate how long it'll take to load it again
        numCommitsBallpark = settings.history.getRepoNumCommits(repo.workdir)
        if numCommitsBallpark != 0:
            # Reserve second half of progress bar for graph progress
            self.progressRange.emit(0, 2*numCommitsBallpark)

        # ---------------------------------------------------------------------
        # Build commit sequence

        self.progressAbortable.emit(True)

        truncatedHistory = False
        for offsetFromTop, commit in enumerate(walker):
            commitSequence.append(commit)

            # Comment this out to waste CPU time and slow things down
            if offsetFromTop == 0 or offsetFromTop % PROGRESS_INTERVAL != 0:
                continue

            message = self.tr("{0} commits...").format(QLocale().toString(offsetFromTop))
            self.progressMessage.emit(message)
            if numCommitsBallpark > 0 and offsetFromTop <= numCommitsBallpark:
                self.progressValue.emit(offsetFromTop)

            if self._wantAbort:
                message = self.tr("{0} commits. Aborting...").format(QLocale().toString(offsetFromTop))
                self.progressMessage.emit(message)
                truncatedHistory = True
                break

        # Can't abort anymore
        self.progressAbortable.emit(False)

        numCommits = len(commitSequence)
        log.info("loadCommitSequence", F"{state.shortName}: loaded {numCommits} commits")
        graphMessage = self.tr("{0} commits total.").format(QLocale().toString(numCommits))
        if truncatedHistory:
            graphMessage += " " + self.tr("(truncated)", "commit history truncated")
        self.progressMessage.emit(graphMessage)

        if numCommitsBallpark != 0:
            # First half of progress bar was for commit log
            self.progressRange.emit(-numCommits, numCommits)
        else:
            self.progressRange.emit(0, numCommits)
        self.progressValue.emit(0)

        # ---------------------------------------------------------------------
        # Build graph

        graph = Graph()
        graphGenerator = graph.startGenerator()

        # Generate fake "Uncommitted Changes" with HEAD as parent
        commitSequence.insert(0, None)

        state.hiddenCommits = set()
        state.foreignCommits = set()
        hiddenCommitSolver = state.newHiddenCommitSolver()
        foreignCommitSolver = ForeignCommitSolver(state.reverseRefCache)

        for commit in commitSequence:
            if not commit:
                oid = UC_FAKEID
                parents = state._uncommittedChangesFakeCommitParents()
            else:
                oid = commit.oid
                parents = commit.parent_ids

            graphGenerator.newCommit(oid, parents)

            foreignCommitSolver.newCommit(oid, parents, state.foreignCommits)
            hiddenCommitSolver.newCommit(oid, parents, state.hiddenCommits)

            row = graphGenerator.row
            rowInt = int(row)

            assert type(row) == BatchRow
            assert rowInt >= 0
            graph.commitRows[oid] = row

            # Save keyframes at regular intervals for faster random access.
            if rowInt % KF_INTERVAL == 0:
                graph.saveKeyframe(graphGenerator)
                self.progressValue.emit(rowInt)

        self.progressValue.emit(numCommits)

        log.verbose("loadCommitSequence", "Peak arc count:", graphGenerator.peakArcCount)

        state.commitSequence = commitSequence
        state.graph = graph

        # ---------------------------------------------------------------------
        # RETURN TO UI THREAD
        # ---------------------------------------------------------------------
        yield from self.flowEnterUiThread()

        # Assign state to RepoWidget
        rw.state = state

        # Save commit count (if not truncated)
        if not truncatedHistory:
            settings.history.setRepoNumCommits(repo.workdir, numCommits)

        # Bump repo in history
        settings.history.addRepo(repo.workdir)
        settings.history.setRepoSuperproject(repo.workdir, state.superproject)
        settings.history.write()
        rw.window().fillRecentMenu()  # TODO: emit signal instead?

        # Finally prime the UI
        with QSignalBlockerContext(rw.graphView, rw.sidebar):
            rw.graphView.setHiddenCommits(state.hiddenCommits)
            rw.graphView.setCommitSequence(commitSequence)

            collapseCache = state.uiPrefs.collapseCache
            if collapseCache:
                rw.sidebar.collapseCache = set(collapseCache)
                rw.sidebar.collapseCacheValid = True
            rw.sidebar.refresh(state)

            rw.graphView.selectUncommittedChanges(force=True)

        # Restore main UI
        rw.removePlaceholderWidget()

        # Refresh tab text
        rw.nameChange.emit()

        # Scrolling HEAD into view isn't super intuitive if we boot to Uncommitted Changes
        # if newState.activeCommitOid:
        #     rw.graphView.scrollToCommit(newState.activeCommitOid, QAbstractItemView.ScrollHint.PositionAtCenter)

        # Focus on some interesting widget within the RepoWidget after loading the repo.
        # (delay to next event loop so Qt has time to show the widget first)
        QTimer.singleShot(0, rw.setInitialFocus)

        # Load the workdir
        yield from self.flowSubtask(Jump, NavLocator(NavContext.WORKDIR))

    def onError(self, exc: Exception):
        self.rw.state = None
        # TODO: rw failure card?
        super().onError(exc)


class LoadWorkdir(RepoTask):
    def canKill(self, task: RepoTask):
        if type(task) is LoadWorkdir:
            log.warning(TAG, "LoadWorkdir is killing another LoadWorkdir. This is inefficient!")
            return True
        return type(task) in [LoadCommit, LoadPatch]

    def flow(self, allowWriteIndex: bool):
        yield from self.flowEnterWorkerThread()

        with Benchmark("LoadWorkdir/Index"):
            self.repo.refresh_index()

        yield from self.flowEnterWorkerThread()  # let task thread be interrupted here
        with Benchmark("LoadWorkdir/Staged"):
            self.stageDiff = self.repo.get_staged_changes()

        yield from self.flowEnterWorkerThread()  # let task thread be interrupted here
        with Benchmark("LoadWorkdir/Unstaged"):
            self.dirtyDiff = self.repo.get_unstaged_changes(allowWriteIndex)


class LoadCommit(RepoTask):
    def canKill(self, task: RepoTask):
        return type(task) in [LoadWorkdir, LoadCommit, LoadPatch]

    def flow(self, oid: Oid):
        yield from self.flowEnterWorkerThread()
        self.diffs = self.repo.commit_diffs(oid)
        self.message = self.repo.get_commit_message(oid)


class LoadPatch(RepoTask):
    def effects(self) -> TaskEffects:
        return TaskEffects.Nothing  # let custom callback in RepoWidget do it

    def canKill(self, task: RepoTask):
        return type(task) in [LoadPatch]

    def _processPatch(self, patch: Patch, locator: NavLocator
                      ) -> DiffDocument | SpecialDiffError | DiffConflict | DiffImagePair:
        if not patch:
            locator = locator.withExtraFlags(NavFlags.ForceRefreshWorkdir)
            message = locator.toHtml(self.tr("The file appears to have changed on disk since we cached it. "
                                             "[Try to refresh it.]"))
            return SpecialDiffError(self.tr("Outdated diff."), message,
                                    icon=QStyle.StandardPixmap.SP_MessageBoxWarning)

        if not patch.delta:
            # Rare libgit2 bug, should be fixed in 1.6.0
            return SpecialDiffError(self.tr("Patch has no delta!"), icon=QStyle.StandardPixmap.SP_MessageBoxWarning)

        if patch.delta.status == GIT_DELTA_CONFLICTED:
            ancestor, ours, theirs = self.repo.index.conflicts[patch.delta.new_file.path]
            return DiffConflict(ancestor, ours, theirs)

        submodule = None
        with (contextlib.suppress(KeyError),
              contextlib.suppress(ValueError),  # "submodule <whatever> has not been added yet" (GIT_EEXISTS)
              Benchmark("Submodule detection")
              ):
            submodule = self.repo.lookup_submodule(patch.delta.new_file.path)
        if submodule:
            return SpecialDiffError.submoduleDiff(self.repo, submodule, patch)

        try:
            diffModel = DiffDocument.fromPatch(patch, locator)
            diffModel.document.moveToThread(QApplication.instance().thread())
            return diffModel
        except SpecialDiffError as dme:
            return dme
        except ShouldDisplayPatchAsImageDiff:
            return DiffImagePair(self.repo, patch.delta, locator)
        except BaseException as exc:
            summary, details = excStrings(exc)
            return SpecialDiffError(summary, icon=QStyle.StandardPixmap.SP_MessageBoxCritical, preformatted=details)

    def flow(self, patch: Patch, locator: NavLocator):
        yield from self.flowEnterWorkerThread()
        self.result = self._processPatch(patch, locator)
