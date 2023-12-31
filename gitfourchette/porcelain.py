from gitfourchette import log as _log
from pathlib import Path as _Path

from pygit2 import (
    Blob,
    Branch,
    CheckoutCallbacks,
    Commit,
    Config as GitConfig,
    Diff,
    DiffDelta,
    DiffFile,
    DiffLine,
    DiffHunk,
    GitError,
    Keypair,
    IndexEntry,
    InvalidSpecError,
    Oid,
    Patch,
    Remote,
    RemoteCallbacks,
    Repository as _VanillaRepository,
    Signature,
    Stash,
    StashApplyCallbacks,
    Submodule,
    Tree,
    Walker,
)

from pygit2 import (
    __version__ as PYGIT2_VERSION,
    LIBGIT2_VERSION,
)

from pygit2 import (
    GIT_APPLY_LOCATION_BOTH,
    GIT_APPLY_LOCATION_INDEX,
    GIT_APPLY_LOCATION_WORKDIR,
    GIT_BRANCH_ALL,
    GIT_BRANCH_LOCAL,
    GIT_BRANCH_REMOTE,
    GIT_CHECKOUT_DISABLE_PATHSPEC_MATCH,
    GIT_CHECKOUT_FORCE,
    GIT_CHECKOUT_NOTIFY_CONFLICT,
    GIT_CHECKOUT_REMOVE_UNTRACKED,
    GIT_CREDENTIAL_DEFAULT,
    GIT_CREDENTIAL_SSH_CUSTOM,
    GIT_CREDENTIAL_SSH_INTERACTIVE,
    GIT_CREDENTIAL_SSH_KEY,
    GIT_CREDENTIAL_SSH_MEMORY,
    GIT_CREDENTIAL_USERNAME,
    GIT_CREDENTIAL_USERPASS_PLAINTEXT,
    GIT_DELTA_ADDED,
    GIT_DELTA_CONFLICTED,
    GIT_DELTA_DELETED,
    GIT_DELTA_IGNORED,
    GIT_DELTA_MODIFIED,
    GIT_DELTA_RENAMED,
    GIT_DELTA_TYPECHANGE,
    GIT_DELTA_UNMODIFIED,
    GIT_DELTA_UNTRACKED,
    GIT_DIFF_INCLUDE_UNTRACKED,
    GIT_DIFF_NORMAL,
    GIT_DIFF_RECURSE_UNTRACKED_DIRS,
    GIT_DIFF_SHOW_BINARY,
    GIT_DIFF_SHOW_UNTRACKED_CONTENT,
    GIT_DIFF_UPDATE_INDEX,
    GIT_FETCH_NO_PRUNE,
    GIT_FETCH_PRUNE,
    GIT_FILEMODE_BLOB,
    GIT_FILEMODE_BLOB_EXECUTABLE,
    GIT_FILEMODE_COMMIT,
    GIT_FILEMODE_LINK,
    GIT_FILEMODE_TREE,
    GIT_MERGE_ANALYSIS_FASTFORWARD,
    GIT_MERGE_ANALYSIS_NORMAL,
    GIT_MERGE_ANALYSIS_UP_TO_DATE,
    GIT_MERGE_PREFERENCE_FASTFORWARD_ONLY,
    GIT_MERGE_PREFERENCE_NONE,
    GIT_MERGE_PREFERENCE_NO_FASTFORWARD,
    GIT_OBJ_COMMIT,
    GIT_REF_OID,
    GIT_REF_SYMBOLIC,
    GIT_RESET_HARD,
    GIT_RESET_MIXED,
    GIT_RESET_SOFT,
    GIT_REPOSITORY_OPEN_NO_SEARCH,
    GIT_SORT_NONE,
    GIT_SORT_REVERSE,
    GIT_SORT_TIME,
    GIT_SORT_TOPOLOGICAL,
    GIT_STATUS_INDEX_DELETED,
    GIT_STATUS_INDEX_MODIFIED,
    GIT_STATUS_INDEX_NEW,
    GIT_STATUS_INDEX_RENAMED,
    GIT_STATUS_INDEX_TYPECHANGE,
    GIT_STATUS_WT_DELETED,
    GIT_STATUS_WT_MODIFIED,
    GIT_STATUS_WT_NEW,
    GIT_STATUS_WT_RENAMED,
    GIT_STATUS_WT_TYPECHANGE,
    GIT_STATUS_WT_UNREADABLE,
)

try:
    # pygit2 1.14+
    from pygit2.remotes import TransferProgress
except ImportError:
    # TODO: Nuke this once we drop compatibility with old pygit2 versions (1.13 and older)
    from pygit2.remote import TransferProgress

import contextlib as _contextlib
import os as _os
import re as _re
import typing as _typing


_TAG = "porcelain"

NULL_OID = Oid(raw=b'')

CORE_STASH_MESSAGE_PATTERN = _re.compile(r"^On ([^\s:]+|\(no branch\)): (.+)")
WINDOWS_RESERVED_FILENAMES_PATTERN = _re.compile(r"(.*/)?(AUX|COM[1-9]|CON|LPT[1-9]|NUL|PRN)($|\.|/)", _re.IGNORECASE)
DIFF_HEADER_PATTERN = _re.compile(r"^diff --git (\"?\w/[^\"]+\"?) (\"?\w/[^\"]+\"?)")

GIT_STATUS_INDEX_MASK = (
        GIT_STATUS_INDEX_NEW
        | GIT_STATUS_INDEX_MODIFIED
        | GIT_STATUS_INDEX_DELETED
        | GIT_STATUS_INDEX_RENAMED
        | GIT_STATUS_INDEX_TYPECHANGE)

GIT_STATUS_WT_MASK = (
        GIT_STATUS_WT_NEW
        | GIT_STATUS_WT_MODIFIED
        | GIT_STATUS_WT_DELETED
        | GIT_STATUS_WT_TYPECHANGE
        | GIT_STATUS_WT_RENAMED
        | GIT_STATUS_WT_UNREADABLE)


class RefPrefix:
    HEADS = "refs/heads/"
    REMOTES = "refs/remotes/"
    TAGS = "refs/tags/"

    @classmethod
    def split(cls, refname: str):
        for prefix in cls.HEADS, cls.REMOTES, cls.TAGS:
            if refname.startswith(prefix):
                return prefix, refname[len(prefix):]
        return "", refname


class NameValidationError(ValueError):
    CANNOT_BE_EMPTY = 0
    ILLEGAL_NAME = 1
    ILLEGAL_PREFIX = 2
    ILLEGAL_SUFFIX = 3
    CONTAINS_ILLEGAL_CHAR = 4
    CONTAINS_ILLEGAL_SEQ = 5
    NOT_WINDOWS_FRIENDLY = 6
    NAME_TAKEN = 7

    def __init__(self, code: int):
        super().__init__(F"Name validation failed ({code})")
        self.code = code


class DivergentBranchesError(Exception):
    def __init__(self, local_branch: Branch, remote_branch: Branch):
        super().__init__()
        self.local_branch = local_branch
        self.remote_branch = remote_branch

    def __str__(self):
        return f"DivergentBranchesError(local: {self.local_branch.shorthand}, remote: {self.remote_branch.shorthand})"


class ConflictError(Exception):
    def __init__(self, conflicts: list[str], description="Conflicts"):
        super().__init__(description)
        self.description = description
        self.conflicts = conflicts

    def __str__(self):
        return f"ConflictError({len(self.conflicts)}, {self.description})"


class MultiFileError(Exception):
    file_exceptions: dict[str, Exception]

    def __init__(self):
        self.file_exceptions = {}

    def add_file_error(self, path: str, exc: Exception):
        self.file_exceptions[path] = exc

    def __bool__(self):
        return bool(self.file_exceptions)


class CheckoutBreakdown(CheckoutCallbacks):
    status: dict[str, int]

    def __init__(self):
        super().__init__()
        self.status = dict()

    def checkout_notify(self, why: int, path: str, baseline=None, target=None, workdir=None):
        self.status[path] = why

    def get_conflicts(self):
        return [path for path in self.status
                if self.status[path] == GIT_CHECKOUT_NOTIFY_CONFLICT]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not exc_type:
            return False
        if issubclass(exc_type, GitError):
            message = str(exc_val)
            if "prevents checkout" in message or "prevent checkout" in message:
                conflicts = self.get_conflicts()
                if conflicts:
                    raise ConflictError(conflicts, "workdir")
        return False  # let error propagate


class StashApplyBreakdown(StashApplyCallbacks, CheckoutBreakdown):
    def stash_apply_progress(self, pr):
        _log.info(_TAG, f"stash apply progress: {pr}")


def _version_at_least(
        package_name: str,
        required_version_string: str,
        current_version_string: str,
        raise_error=True,
        feature_name="This feature"
):
    def version_to_tuple(s: str):
        v = []
        for n in s.split("."):
            try:
                v.append(int(n))
            except ValueError:
                v.append(0)
        # Trim trailing zeros to ease comparison
        while v and v[-1] == 0:
            v.pop()
        return tuple(v)

    required_version = version_to_tuple(required_version_string)
    current_version = version_to_tuple(current_version_string)

    if tuple(current_version) < tuple(required_version):
        if not raise_error:
            return False

        message = (f"{feature_name} requires {package_name} v{required_version_string} or later "
                   f"(you have v{current_version_string}).")
        raise NotImplementedError(message)

    return True


def pygit2_version_at_least(required_version: str, raise_error=True, feature_name="This feature"):
    return _version_at_least(
        package_name="pygit2",
        required_version_string=required_version,
        current_version_string=PYGIT2_VERSION,
        raise_error=raise_error,
        feature_name=feature_name)


def libgit2_version_at_least(required_version: str, raise_error=True, feature_name="This feature"):
    return _version_at_least(
        package_name="libgit2",
        required_version_string=required_version,
        current_version_string=LIBGIT2_VERSION,
        raise_error=raise_error,
        feature_name=feature_name)


def split_remote_branch_shorthand(remote_branch_name: str) -> tuple[str, str]:
    """
    Extract the remote name and branch name from a remote branch shorthand
    string such as "origin/master".

    The input string must not start with "refs/remotes/".

    Note: results can be flaky if the remote contains a slash in its name.
    """

    if remote_branch_name.startswith("refs/"):
        raise ValueError("remote branch shorthand name must not start with refs/")

    # TODO: extraction of branch name is flaky if remote name or branch name contains slashes
    try:
        remote_name, branchName = remote_branch_name.split("/", 1)
        return remote_name, branchName
    except ValueError:
        # `git svn clone` creates .git/refs/remotes/git-svn, which trips up pygit2
        return remote_branch_name, ""


def validate_refname(name: str, reserved_names: list[str]):
    """
    Checks the validity of a ref name according to `man git-check-ref-format`.
    Raises NameValidationError if the name is incorrect.
    """

    E = NameValidationError

    # Can't be empty
    if not name:
        raise E(E.CANNOT_BE_EMPTY)

    # Rule 9: can't be single character '@'
    elif name == '@':
        raise E(E.ILLEGAL_NAME)

    # Rule 4: forbid space, tilde, caret, colon
    # Rule 5: forbid question mark, asterisk, open bracket
    # Rule 10: forbid backslash
    elif any(c in " ~^:[?*\\" for c in name):
        raise E(E.CONTAINS_ILLEGAL_CHAR)

    # Rule 1: slash-separated components can't start with dot or end with .lock
    # Rule 3: forbid consecutive dots
    # Rule 6: forbid consecutive slashes
    # Rule 8: forbid '@{'
    elif any(seq in name for seq in ["/.", ".lock/", "..", "//", "@{"]):
        raise E(E.CONTAINS_ILLEGAL_SEQ)

    # Rule 1: can't start with dot
    # Rule 6: can't start with slash
    elif name.startswith((".", "/")):
        raise E(E.ILLEGAL_PREFIX)

    # Rule 1: can't end with .lock
    # Rule 6: can't end with slash
    # Rule 7: can't end with dot
    elif name.endswith((".lock", "/", ".")):
        raise E(E.ILLEGAL_SUFFIX)

    # Prevent filenames that are reserved on Windows
    elif WINDOWS_RESERVED_FILENAMES_PATTERN.match(name):
        raise E(E.NOT_WINDOWS_FRIENDLY)

    elif name.lower() in (n.lower() for n in reserved_names):
        raise E(E.NAME_TAKEN)


def validate_signature_item(s: str):
    """
    Checks the validity of the name or email in a signature according to `libgit2/signature.c`.
    Raises NameValidationError if the item is incorrect.
    """

    E = NameValidationError

    # Angle bracket characters are not allowed
    if "<" in s or ">" in s:
        raise E(E.CONTAINS_ILLEGAL_CHAR)

    # Trim crud from name
    def is_crud(c: str):
        return ord(c) <= 32 or c in ".,:;<>\"\\'"

    start = 0
    end = len(s)
    while end > 0 and is_crud(s[end-1]):
        end -= 1
    while start < end and is_crud(s[start]):
        start += 1
    trimmed = s[start:end]

    # Cannot be empty after trimming
    if not trimmed:
        raise E(E.CANNOT_BE_EMPTY)


def get_git_global_identity() -> tuple[str, str]:
    """
    Returns the name and email set in the global `.gitconfig` file.
    If the global identity isn't set, this function returns blank strings.
    """

    name = ""
    email = ""

    try:
        global_config = GitConfig.get_global_config()
    except OSError:
        # "The global file '.gitconfig' doesn't exist: No such file or directory
        return name, email

    with _contextlib.suppress(KeyError):
        name = global_config["user.name"]

    with _contextlib.suppress(KeyError):
        email = global_config["user.email"]

    return name, email


def DiffFile_compare(f1: DiffFile, f2: DiffFile):
    # TODO: pygit2 ought to implement DiffFile.__eq__
    same = f1.id == f2.id
    same &= f1.mode == f2.mode
    same &= f1.flags == f2.flags
    same &= f1.raw_path == f2.raw_path
    if same:
        assert f1.path == f2.path
        assert f1.size == f2.size
    return same


def strip_stash_message(stash_message: str) -> str:
    m = CORE_STASH_MESSAGE_PATTERN.match(stash_message)
    if m:
        return m.group(2)
    else:
        return stash_message


class Repo(_VanillaRepository):
    """
    Drop-in replacement for pygit2.Repository with convenient front-ends to common git operations.
    """

    def __del__(self):
        _log.verbose(_TAG, "__del__ Repo")
        self.free()

    @property
    def head_tree(self) -> Tree:
        return self.head.peel(Tree)

    @property
    def head_commit(self) -> Commit:
        return self.head.peel(Commit)

    @property
    def head_commit_oid(self) -> Oid:
        return self.head_commit.oid

    @property
    def head_commit_message(self) -> str:
        return self.head_commit.message

    @property
    def head_branch_shorthand(self) -> str:
        return self.head.shorthand

    @property
    def head_branch_fullname(self) -> str:
        return self.head.name

    def peel_commit(self, oid: Oid) -> Commit:
        return self[oid].peel(Commit)

    def peel_blob(self, oid: Oid) -> Blob:
        return self[oid].peel(Blob)

    def peel_tree(self, oid: Oid) -> Tree:
        return self[oid].peel(Tree)

    def in_workdir(self, path: str) -> str:
        """Return an absolutized version of `path` within this repo's workdir."""
        assert not _os.path.isabs(path)
        return _os.path.join(self.workdir, path)

    def refresh_index(self, force: bool = False):
        """
        Reload the index. Call this before manipulating the staging area
        to ensure any external modifications are taken into account.

        This is a fairly cheap operation if the index hasn't changed on disk,
        unless you pass force=True.
        """
        self.index.read(force)

    def get_uncommitted_changes(self, show_binary: bool = False) -> Diff:
        """
        Get a Diff of all uncommitted changes in the working directory,
        compared to the commit at HEAD.

        In other words, this function compares the workdir to HEAD.
        """

        flags = (GIT_DIFF_INCLUDE_UNTRACKED
                 | GIT_DIFF_RECURSE_UNTRACKED_DIRS
                 | GIT_DIFF_SHOW_UNTRACKED_CONTENT
                 )

        if show_binary:
            flags |= GIT_DIFF_SHOW_BINARY

        dirty_diff = self.diff('HEAD', None, cached=False, flags=flags)
        dirty_diff.find_similar()
        return dirty_diff

    def get_unstaged_changes(self, update_index: bool = False, show_binary: bool = False) -> Diff:
        """
        Get a Diff of unstaged changes in the working directory.

        In other words, this function compares the workdir to the index.
        """

        flags = (GIT_DIFF_INCLUDE_UNTRACKED
                 | GIT_DIFF_RECURSE_UNTRACKED_DIRS
                 | GIT_DIFF_SHOW_UNTRACKED_CONTENT
                 )

        # Don't attempt to update the index if the repo is locked for writing
        update_index &= _os.access(self.path, _os.W_OK)

        # GIT_DIFF_UPDATE_INDEX may improve performance for subsequent diffs if the
        # index was stale, but this requires the repo to be writable.
        if update_index:
            _log.verbose(_TAG, "GIT_DIFF_UPDATE_INDEX")
            flags |= GIT_DIFF_UPDATE_INDEX

        if show_binary:
            flags |= GIT_DIFF_SHOW_BINARY

        dirty_diff = self.diff(None, None, flags=flags)
        # dirty_diff.find_similar()  #-- it seems that find_similar cannot find renames in unstaged changes, so don't bother
        return dirty_diff

    def get_staged_changes(self, fast: bool = False, show_binary: bool = False) -> Diff:
        """
        Get a Diff of the staged changes.

        In other words, this function compares the index to HEAD.
        """

        flags = GIT_DIFF_NORMAL

        if show_binary:
            flags |= GIT_DIFF_SHOW_BINARY

        if self.head_is_unborn:  # can't compare against HEAD (empty repo or branch pointing nowhere)
            index_tree_oid = self.index.write_tree()
            tree = self.peel_tree(index_tree_oid)
            return tree.diff_to_tree(swap=True, flags=flags)
        else:
            stage_diff: Diff = self.diff('HEAD', None, cached=True, flags=flags)  # compare HEAD to index
            if not fast:
                stage_diff.find_similar()
            return stage_diff

    @property
    def any_conflicts(self) -> bool:
        """True if there are any conflicts in the index."""
        return bool(self.index.conflicts)

    @property
    def any_staged_changes(self) -> bool:
        """True if there are any staged changes in the index."""
        return 0 != len(self.get_staged_changes(fast=True))
        # ---This also works, but it's slower.
        # status = repo.status(untracked_files="no")
        # return any(0 != (flag & GIT_STATUS_INDEX_MASK) for flag in status.values())

    def commit_diffs(self, oid: Oid, show_binary: bool = False) -> list[Diff]:
        """
        Get a list of Diffs of a commit compared to its parents.
        """
        flags = GIT_DIFF_NORMAL

        if show_binary:
            flags |= GIT_DIFF_SHOW_BINARY

        commit: Commit = self.get(oid)

        if commit.parents:
            all_diffs = []

            parent: Commit
            for i, parent in enumerate(commit.parents):
                if i == 0:
                    diff = self.diff(parent, commit, flags=flags)
                    diff.find_similar()
                    all_diffs.append(diff)
                elif not parent.parents:
                    # This parent is parentless: assume merging in new files from this parent
                    # (e.g. "untracked files on ..." parents of stash commits)
                    tree: Tree = parent.peel(Tree)
                    diff = tree.diff_to_tree(swap=True, flags=flags)
                    all_diffs.append(diff)
                else:
                    # Skip non-parentless parent in merge commits
                    pass

            return all_diffs

        else:
            # Parentless commit: diff with empty tree
            # (no tree passed to diff_to_tree == force diff against empty tree)
            diff = commit.tree.diff_to_tree(swap=True, flags=flags)
            return [diff]

    def checkout_local_branch(self, name: str):
        """Switch to a local branch."""
        branch = self.branches.local[name]
        with CheckoutBreakdown() as callbacks:
            self.checkout(branch.raw_name, callbacks=callbacks)

    def checkout_ref(self, refname: str):
        """Enter detached HEAD on the commit pointed to by a ref."""
        with CheckoutBreakdown() as callbacks:
            self.checkout(refname, callbacks=callbacks)

    def checkout_commit(self, oid: Oid):
        """Enter detached HEAD on a commit."""
        commit = self.peel_commit(oid)
        with CheckoutBreakdown() as callbacks:
            self.checkout_tree(commit.tree, callbacks=callbacks)
            self.set_head(oid)

    def revert_commit_in_workdir(self, oid: Oid):
        """Revert a commit and check out the reverted index if there are no conflicts
        with the workdir."""

        trash_commit = self.peel_commit(oid)
        head_commit = self.head_commit
        revert_index = self.revert_commit(trash_commit, head_commit)

        if revert_index.conflicts:
            early_conflicts = []
            for common_ancestor, ours, theirs in revert_index.conflicts:
                # Figure out a path to display (note that elements of the 3-tuple may be None!)
                for candidate in [common_ancestor, ours, theirs]:
                    if candidate and candidate.path:
                        early_conflicts.append(candidate.path)
                        break
            raise ConflictError(early_conflicts, "HEAD")

        with CheckoutBreakdown() as callbacks:
            self.checkout_index(revert_index, callbacks=callbacks)

    def rename_local_branch(self, name: str, new_name: str) -> Branch:
        """Rename a local branch."""
        # TODO: if the branch tracks an upstream branch, issue a warning that it won't be renamed on the server
        branch = self.branches.local[name]
        branch.rename(new_name)
        return branch

    def delete_local_branch(self, name: str):
        """Delete a local branch."""
        # TODO: if remote-tracking, let user delete upstream too?
        self.branches.local.delete(name)

    def create_branch_on_head(self, name: str) -> Branch:
        """Create a local branch pointing to the commit at the current HEAD."""
        return self.create_branch(name, self.head_commit)

    def create_branch_tracking(self, name: str, remote_branch_name: str) -> Branch:
        """Create a local branch pointing to the commit at the tip of a remote branch,
        and set up the local branch to track the remote branch."""
        remote_branch = self.branches.remote[remote_branch_name]
        commit: Commit = remote_branch.peel(Commit)
        branch = self.create_branch(name, commit)
        branch.upstream = remote_branch
        return branch

    def create_branch_from_commit(self, name: str, oid: Oid) -> Branch:
        """Create a local branch pointing to the given commit oid."""
        commit = self.peel_commit(oid)
        branch = self.create_branch(name, commit)
        return branch

    def listall_remote_branches(self) -> dict[str, list[str]]:
        names = {}

        # Create empty lists for all remotes (including branchless remotes)
        for remote in self.remotes:
            names[remote.name] = []

        for refname in self.listall_references():
            prefix, shorthand = RefPrefix.split(refname)

            if prefix != RefPrefix.REMOTES:
                continue

            if refname.endswith("/HEAD"):
                # Skip refs/remotes/*/HEAD (the remote's default branch).
                # The ref file (.git/refs/remotes/*/HEAD) is created ONCE when first cloning the repository,
                # and it's never updated again automatically, even if the default branch has changed on the remote.
                # It's a symbolic branch, so looking up a stale version of the remote's HEAD may raise KeyError.
                # It's just not worth the trouble.
                # See: https://stackoverflow.com/questions/8839958
                continue

            remoteName, branchName = split_remote_branch_shorthand(shorthand)
            names[remoteName].append(branchName)

        return names

    def generate_unique_local_branch_name(self, seed: str):
        """Generate a name that doesn't clash with any existing local branches."""

        i = 1
        name = seed
        all_local_branches = list(self.branches.local)

        while name in all_local_branches:
            i += 1
            name = F"{seed}-{i}"

        return name

    def generate_unique_branch_name_on_remote(self, remote: str, seed: str):
        """Generate a name that doesn't clash with any existing branches on the remote."""

        i = 1
        name = seed
        all_remote_branches = list(self.branches.remote)

        while f"{remote}/{name}" in all_remote_branches:
            i += 1
            name = F"{seed}-{i}"

        return name

    def listall_tags(self) -> list[str]:
        return [
            name.removeprefix(RefPrefix.TAGS)
            for name in self.listall_references()
            if name.startswith(RefPrefix.TAGS)
        ]

    def edit_tracking_branch(self, local_branch_name: str, remote_branch_name: str):
        local_branch = self.branches.local[local_branch_name]
        if remote_branch_name:
            remote_branch = self.branches.remote[remote_branch_name]
            local_branch.upstream = remote_branch
        else:
            if local_branch.upstream is not None:
                local_branch.upstream = None

    def create_remote(self, name: str, url: str):
        self.remotes.create(name, url)

    def edit_remote(self, name: str, new_name: str, new_url: str):
        self.remotes.set_url(name, new_url)
        if name != new_name:
            self.remotes.rename(name, new_name)  # rename AFTER setting everything else!

    def delete_remote(self, name: str):
        self.remotes.delete(name)

    def delete_remote_branch(self, remote_branch_name: str, remoteCallbacks: RemoteCallbacks):
        remoteName, branchName = split_remote_branch_shorthand(remote_branch_name)

        refspec = f":{RefPrefix.HEADS}{branchName}"
        _log.info(_TAG, f"Delete remote branch: refspec: \"{refspec}\"")

        remote = self.remotes[remoteName]
        remote.push([refspec], callbacks=remoteCallbacks)

    def rename_remote_branch(self, old_remote_branch_name: str, new_name: str, remote_callbacks: RemoteCallbacks):
        """
        Warning: this function does not refresh the state of the remote branch before renaming it!
        """
        remoteName, oldBranchName = split_remote_branch_shorthand(old_remote_branch_name)

        # First, make a new branch pointing to the same ref as the old one
        refspec1 = f"{RefPrefix.REMOTES}{old_remote_branch_name}:{RefPrefix.HEADS}{new_name}"

        # Next, delete the old branch
        refspec2 = f":{RefPrefix.HEADS}{oldBranchName}"

        _log.info(_TAG, f"Rename remote branch: remote: {remoteName}; refspec: {[refspec1, refspec2]}")

        remote = self.remotes[remoteName]
        remote.push([refspec1, refspec2], callbacks=remote_callbacks)

    def delete_stale_remote_head_symbolic_ref(self, remote_name: str):
        """
        Delete `refs/remotes/{remoteName}/HEAD` to work around a bug in libgit2
        where `git_revwalk__push_glob` errors out on that symbolic ref
        if it points to a branch that doesn't exist anymore.

        This bug may prevent fetching.
        """

        head_refname = f"{RefPrefix.REMOTES}{remote_name}/HEAD"
        head_ref = self.references.get(head_refname)

        # Only risk deleting remote HEAD if it's symbolic
        if head_ref and head_ref.type == GIT_REF_SYMBOLIC:
            try:
                head_ref.resolve()
            except KeyError:  # pygit2 wraps GIT_ENOTFOUND with KeyError
                # Stale -- nuke it
                self.references.delete(head_refname)
                _log.info(_TAG, "Deleted stale remote HEAD symbolic ref: " + head_refname)

    def fetch_remote(self, remote_name: str, remote_callbacks: RemoteCallbacks) -> TransferProgress:
        # Delete `refs/remotes/{remoteName}/HEAD` before fetching.
        # See docstring for that function for why.
        self.delete_stale_remote_head_symbolic_ref(remote_name)

        remote = self.remotes[remote_name]
        transfer = remote.fetch(callbacks=remote_callbacks, prune=GIT_FETCH_PRUNE)
        return transfer

    def fetch_remote_branch(
            self, remote_branch_name: str, remote_callbacks: RemoteCallbacks
    ) -> TransferProgress:
        remoteName, branchName = split_remote_branch_shorthand(remote_branch_name)

        # Delete .git/refs/{remoteName}/HEAD to work around a bug in libgit2
        # where git_revwalk__push_glob chokes on refs/remotes/{remoteName}/HEAD
        # if it points to a branch that doesn't exist anymore.
        self.delete_stale_remote_head_symbolic_ref(remoteName)

        remote = self.remotes[remoteName]
        transfer = remote.fetch(refspecs=[branchName], callbacks=remote_callbacks, prune=GIT_FETCH_NO_PRUNE)
        return transfer

    def reset_head2(self, onto: Oid, mode: _typing.Literal["soft", "mixed", "hard"], recurse_submodules: bool = False):
        modes = {
            "soft": GIT_RESET_SOFT,
            "mixed": GIT_RESET_MIXED,
            "hard": GIT_RESET_HARD,
        }
        self.reset(onto, modes[mode])
        if recurse_submodules:
            raise NotImplementedError("reset HEAD + recurse submodules not implemented yet!")

    def get_commit_message(self, oid: Oid) -> str:
        commit = self.peel_commit(oid)
        return commit.message

    def create_commit_on_head(
            self,
            message: str,
            author: Signature | None = None,
            committer: Signature | None = None
    ) -> Oid:
        """
        Create a commit with the contents of the index tree.
        Use the commit at HEAD as the new commit's parent.
        If `author` or `committer` are not overridden, use the repository's default_signature.
        """

        if self.head_is_detached:
            ref_to_update = "HEAD"
        else:
            # Get the ref name pointed to by HEAD, but DON'T use repo.head! It won't work if HEAD is unborn.
            # Both git and libgit2 store a default branch name in .git/HEAD when they init a repo,
            # so we should always have a ref name, even though it might not point to anything.
            ref_to_update = self.lookup_reference("HEAD").target

        if self.head_is_unborn:
            parents = []
        else:
            parents = [self.head_commit_oid]

        index_tree_oid = self.index.write_tree()

        # Take default signature now to prevent any timestamp diff between author and committer
        fallback_signature = self.default_signature

        new_commit_oid = self.create_commit(
            ref_to_update,
            author or fallback_signature,
            committer or fallback_signature,
            message,
            index_tree_oid,
            parents
        )

        # Repository.create_commit flushes the staged changes from the in-memory index.
        # Write the index to disk so that other applications can pick up the updated staging area.
        self.index.write()

        assert not self.head_is_unborn, "HEAD is still unborn after we have committed!"

        return new_commit_oid

    def amend_commit_on_head(
            self,
            message: str,
            author: Signature | None = None,
            committer: Signature | None = None
    ) -> Oid:
        """
        Amend the commit at HEAD with the contents of the index tree.
        If `author` is None, don't replace the original commit's author.
        If `committer` is None, use default_signature for the committer's signature.
        """
        index_tree_oid = self.index.write_tree(self)
        new_commit_oid = self.amend_commit(
            self.head_commit,
            'HEAD',
            message=message,
            author=author,
            committer=committer or self.default_signature,
            tree=index_tree_oid
        )
        return new_commit_oid

    def get_commit_oid_from_refname(self, refname: str) -> Oid:
        reference = self.references[refname]
        commit: Commit = reference.peel(Commit)
        return commit.oid

    def get_commit_oid_from_tag_name(self, tagname: str) -> Oid:
        assert not tagname.startswith("refs/")
        return self.get_commit_oid_from_refname(RefPrefix.TAGS + tagname)

    def map_refs_to_oids(self) -> dict[str, Oid]:
        """
        Return commit oids at the tip of all branches, tags, etc. in the repository.

        To ensure a consistent outcome across multiple walks of the same commit graph,
        the oids are sorted by ascending commit time.
        """

        tips: list[tuple[str, Commit]] = []

        # Always add 'HEAD' if we have one
        if not self.head_is_unborn:
            try:
                tips.append(("HEAD", self.head_commit))
            except InvalidSpecError as e:
                _log.info(_TAG, F"{e} - Skipping detached HEAD")
                pass

        for ref in self.listall_reference_objects():
            if (ref.type != GIT_REF_OID  # Skip symbolic references
                    or ref.name == "refs/stash"):  # Stashes are dealt with separately
                continue

            try:
                commit: Commit = ref.peel(Commit)
                tips.append((ref.name, commit))
            except InvalidSpecError as e:
                # Some refs might not be committish, e.g. in linux's source repo
                _log.info(_TAG, F"{e} - Skipping ref '{ref.name}'")
                pass

        for i, stash in enumerate(self.listall_stashes()):
            try:
                commit = self.peel_commit(stash.commit_id)
                tips.append((f"stash@{{{i}}}", commit))
            except InvalidSpecError as e:
                _log.info(_TAG, F"{e} - Skipping stash '{stash.message}'")
                pass

        # Reinsert all tips in chronological order
        # (In Python 3.7+, dict key order is stable)
        tips.sort(key=lambda item: item[1].commit_time)
        return dict((ref, commit.oid) for ref, commit in tips)

    def listall_refs_pointing_at(self, oid: Oid):
        refs = []

        # Detached HEAD isn't in repo.references
        if self.head_is_detached and type(self.head.target) == Oid and self.head.target == oid:
            refs.append('HEAD')

        for ref in self.references.objects:
            ref_key = ref.name

            if type(ref.target) != Oid:
                # Symbolic reference
                _log.verbose(_TAG, F"Skipping symbolic reference {ref_key} --> {ref.target}")
                continue

            if ref.target != oid:
                continue

            assert ref_key.startswith("refs/")

            if ref_key == "refs/stash":
                # Stashes must be dealt with separately
                continue

            refs.append(ref_key)

        for stash_index, stash in enumerate(self.listall_stashes()):
            if stash.commit_id == oid:
                refs.append(F"stash@{{{stash_index}}}")

        return refs

    def stage_files(self, patches: list[Patch]):
        index = self.index
        for patch in patches:
            if patch.delta.status == GIT_DELTA_DELETED:
                index.remove(patch.delta.new_file.path)
            else:
                index.add(patch.delta.new_file.path)
        index.write()

    def restore_files(self, paths: list[str]):
        """
        Resets the given files to their state at the HEAD commit.
        Any staged, unstaged, or untracked changes in those files will be lost.
        NOTE: This will not
        """

        assert not self.head_is_unborn, "restoreFiles doesn't support unborn HEAD"

        strategy = (GIT_CHECKOUT_FORCE
                    | GIT_CHECKOUT_REMOVE_UNTRACKED
                    | GIT_CHECKOUT_DISABLE_PATHSPEC_MATCH)

        self.checkout_tree(self.head_tree, paths=paths, strategy=strategy)

    def get_staged_tree(self) -> Tree:
        # refresh index before getting indexTree in case an external program modified the staging area
        self.refresh_index(force=False)

        # get tree with staged changes
        index_tree_id = self.index.write_tree()
        index_tree = self[index_tree_id]

        return index_tree

    def discard_files(self, paths: list[str]):
        """
        Discards unstaged changes in the given files.
        Does not discard any changes that are staged.
        """

        strategy = (GIT_CHECKOUT_FORCE
                    | GIT_CHECKOUT_REMOVE_UNTRACKED
                    | GIT_CHECKOUT_DISABLE_PATHSPEC_MATCH)

        # get tree with staged changes
        index_tree = self.get_staged_tree()

        # reset files to their state in the staged tree
        self.checkout_tree(index_tree, paths=paths, strategy=strategy)

    def discard_mode_changes(self, paths: list[str]):
        """
        Discards mode changes in the given files.
        """

        # get tree with staged changes
        index_tree = self.get_staged_tree()

        # reset files to their mode in the staged tree
        for p in paths:
            try:
                mode = index_tree[p].filemode
            except KeyError:
                continue
            if mode in [GIT_FILEMODE_BLOB, GIT_FILEMODE_BLOB_EXECUTABLE]:
                _os.chmod(self.in_workdir(p), mode)

    def unstage_files(self, patches: list[Patch]):
        index = self.index

        head_tree: Tree | None
        if self.head_is_unborn:
            head_tree = None
        else:
            head_tree = self.head_tree

        for patch in patches:
            delta = patch.delta
            old_path = delta.old_file.path
            new_path = delta.new_file.path
            if delta.status == GIT_DELTA_ADDED:
                assert (not head_tree) or (old_path not in head_tree)
                index.remove(old_path)
            elif delta.status == GIT_DELTA_RENAMED:
                # TODO: Two-step removal to completely unstage a rename -- is this what we want?
                assert new_path in index
                index.remove(new_path)
            else:
                assert head_tree
                assert old_path in head_tree
                obj = head_tree[old_path]
                index.add(IndexEntry(old_path, obj.oid, obj.filemode))
        index.write()

    def unstage_mode_changes(self, patches: list[Patch]):
        index = self.index

        for patch in patches:
            of = patch.delta.old_file
            nf = patch.delta.new_file
            if (of.mode != nf.mode
                    and patch.delta.status not in [GIT_DELTA_ADDED, GIT_DELTA_DELETED, GIT_DELTA_UNTRACKED]
                    and of.mode in [GIT_FILEMODE_BLOB, GIT_FILEMODE_BLOB_EXECUTABLE]):
                index.add(IndexEntry(nf.path, nf.id, of.mode))

        index.write()

    def create_stash(self, message: str, paths: list[str]) -> Oid:
        """
        Creates a stash that backs up all changes to the given files.
        Does NOT remove the changes from the workdir (you can use resetFiles afterwards).
        """

        assert paths, "path list cannot be empty"

        try:
            signature = self.default_signature
        except ValueError:
            # Allow creating a stash if the identity isn't set
            signature = Signature(name="UNKNOWN", email="UNKNOWN")

        oid = self.stash(
            stasher=signature,
            message=message,
            keep_index=False,
            keep_all=True,
            include_untracked=False,
            include_ignored=False,
            paths=paths)

        return oid

    def find_stash_index(self, commitOid: Oid) -> int:
        """
        Libgit2 takes an index number to apply/pop/drop stashes. However, it's
        unsafe to cache such an index for the GUI. Instead, we cache the commit ID
        of the stash, and we only convert that to an index when we need to perform
        an operation on the stash. This way, we'll always manipulate the stash
        intended by the user, even if the indices change outside our control.
        """
        try:
            return next(i
                        for i, stash in enumerate(self.listall_stashes())
                        if stash.commit_id == commitOid)
        except StopIteration:
            raise KeyError(f"Stash not found: {commitOid.hex}")

    def stash_apply_oid(self, oid: Oid):
        i = self.find_stash_index(oid)
        with StashApplyBreakdown() as callbacks:
            self.stash_apply(i, callbacks=callbacks)

    def stash_pop_oid(self, oid: Oid):
        i = self.find_stash_index(oid)
        with StashApplyBreakdown() as callbacks:
            self.stash_pop(i, callbacks=callbacks)

    def stash_drop_oid(self, oid: Oid):
        i = self.find_stash_index(oid)
        self.stash_drop(self.find_stash_index(oid))

    def applies_breakdown(self, patch_data: bytes | str, location: int = GIT_APPLY_LOCATION_WORKDIR) -> Diff:
        diff = Diff.parse_diff(patch_data)
        error = MultiFileError()

        # Attempt to apply every patch in the diff separately, so we can report which file an error pertains to
        for patch in diff:
            patch_data = patch.data

            # Work around libgit2 bug: If a patch lacks the "index" line (as our partial patches do),
            # then libgit2 fails to recreate the "---" and "+++" lines. Then it can't parse its own output.
            patch_lines = patch_data.splitlines(True)
            if len(patch_lines) >= 2 and patch_lines[0].startswith(b"diff --git ") and patch_lines[1].startswith(b"@@"):
                header = patch_lines[0].strip().decode("utf-8")
                match = _re.match(DIFF_HEADER_PATTERN, header)
                if match:
                    patch_lines.insert(1, ("--- " + match[1] + "\n").encode("utf-8"))
                    patch_lines.insert(2, ("+++ " + match[2] + "\n").encode("utf-8"))
                    patch_data = b"".join(patch_lines)

            patch_diff = Diff.parse_diff(patch_data)  # can we extract a diff from the patch without re-parsing it?
            try:
                self.applies(patch_diff, location, raise_error=True)
            except (GitError, OSError) as exc:
                error.add_file_error(patch.delta.old_file.path, exc)

        if error:
            raise error
        else:
            return diff

    def apply(self,
              patch_data_or_diff: bytes | str | Diff,
              location: int = GIT_APPLY_LOCATION_WORKDIR
              ) -> Diff:
        if type(patch_data_or_diff) in [bytes, str]:
            diff = Diff.parse_diff(patch_data_or_diff)
        elif type(patch_data_or_diff) is Diff:
            diff = patch_data_or_diff
        else:
            raise TypeError("patchDataOrDiff must be bytes, str, or Diff")

        super().apply(diff, location)
        return diff

    def get_submodule_workdir(self, submo_key: str) -> str:
        submo = self.lookup_submodule(submo_key)
        return self.in_workdir(submo.path)

    def listall_submodules_fast(self) -> list[str]:
        """
        Faster drop-in replacement for pygit2's Repository.listall_submodules (which can be very slow).
        Returns a list of submodule workdirs within the root repo's workdir.
        """

        # return self.listall_submodules()

        config_path = self.in_workdir(".gitmodules")
        if not _os.path.isfile(config_path):
            return []

        config = GitConfig(config_path)
        submo_paths = []
        for configEntry in config:
            key: str = configEntry.name
            if key.startswith("submodule.") and key.endswith(".path"):
                submo_paths.append(configEntry.value)

        return submo_paths

    def fast_forward_branch(self, local_branch_name: str, remote_branch_name: str = ""):
        """
        Fast-forwards a local branch to a remote branch.
        Returns True if the local branch was up-to-date.
        Raises DivergentBranchesError if fast-forwarding is impossible.
        """
        lb = self.branches.local[local_branch_name]

        if not remote_branch_name:
            rb = lb.upstream
            if not rb:
                raise ValueError("Local branch does not track a remote branch")
        else:
            rb = self.branches.remote[remote_branch_name]

        merge_analysis, merge_pref = self.merge_analysis(rb.target, RefPrefix.HEADS + local_branch_name)

        merge_pref_names = {
            GIT_MERGE_PREFERENCE_NONE: "none",
            GIT_MERGE_PREFERENCE_FASTFORWARD_ONLY: "ff only",
            GIT_MERGE_PREFERENCE_NO_FASTFORWARD: "no ff"
        }
        _log.info(_TAG, f"Merge analysis: {merge_analysis}. Merge preference: {merge_pref_names.get(merge_pref, '???')}.")

        if merge_analysis & GIT_MERGE_ANALYSIS_UP_TO_DATE:
            # Local branch is up-to-date with remote branch, nothing to do.
            return True

        elif merge_analysis == (GIT_MERGE_ANALYSIS_NORMAL | GIT_MERGE_ANALYSIS_FASTFORWARD):
            # Go ahead and fast-forward.

            # First, we need to check out the tree pointed to by the remote branch. This step is necessary,
            # otherwise the contents of the commits we're pulling will spill into the unstaged area.
            # Note: checkout_tree defaults to a safe checkout, so it'll raise GitError if any uncommitted changes
            # affect any of the files that are involved in the pull.
            with CheckoutBreakdown() as callbacks:
                self.checkout_tree(rb.peel(Tree), callbacks=callbacks)

            # Then make the local branch point to the same commit as the remote branch.
            lb.set_target(rb.target)

        elif merge_analysis == GIT_MERGE_ANALYSIS_NORMAL:
            # Can't FF. Divergent branches?
            raise DivergentBranchesError(lb, rb)

        else:
            # Unborn or something...
            raise NotImplementedError(F"Unsupported merge analysis {merge_analysis}.")

    def cherrypick(self, oid: Oid):
        super().cherrypick(oid)

    def get_superproject(self) -> str:
        """
        If this repo is a submodule, returns the path to the superproject's working directory,
        otherwise returns None.
        Equivalent to `git rev-parse --show-superproject-working-tree`.
        """

        repo_path = self.path  # e.g. "/home/user/superproj/.git/modules/src/extern/subproj/"
        git_modules_pos = repo_path.rfind("/.git/")

        if git_modules_pos < 0:
            return ""

        outer_wd = repo_path[:git_modules_pos]  # e.g. "/home/user/superproj"

        try:
            tentative_wd = self.config['core.worktree']
            if not _os.path.isabs(tentative_wd):
                tentative_wd = repo_path + "/" + tentative_wd
            tentative_wd = _os.path.normpath(tentative_wd)
            actual_wd = _os.path.normpath(self.workdir)
            if actual_wd == tentative_wd:
                return outer_wd
        except KeyError:
            pass

        return ""

    def get_branch_from_refname(self, refname: str) -> tuple[Branch, bool]:
        prefix, shorthand = RefPrefix.split(refname)
        if prefix == RefPrefix.HEADS:
            return self.branches.local[shorthand], False
        elif prefix == RefPrefix.REMOTES:
            return self.branches.remote[shorthand], True
        raise ValueError("ref is not a local or remote branch")

    def repo_name(self):
        return _os.path.basename(_os.path.normpath(self.workdir))

    def get_local_identity(self) -> tuple[str, str]:
        """
        Return the name and email set in the repository's `.git/config` file.
        If an identity isn't set specifically for this repo, this function returns blank strings.
        """

        # Don't use repo.config because it merges global and local configs
        local_config_path = _os.path.join(self.path, "config")

        name = ""
        email = ""

        if _os.path.isfile(local_config_path):
            local_config = GitConfig(local_config_path)

            with _contextlib.suppress(KeyError):
                name = local_config["user.name"]

            with _contextlib.suppress(KeyError):
                email = local_config["user.email"]

        return name, email

    def delete_tag(self, tagname: str):
        assert not tagname.startswith("refs/")
        refname = RefPrefix.TAGS + tagname
        assert refname in self.references
        self.references.delete(refname)

    def add_inner_repo_as_submodule(self, inner_w: str, remote_url: str, absorb_git_dirs: bool = True):
        outer_w = _Path(self.workdir)
        inner_w = _Path(outer_w, inner_w)  # normalize

        if not inner_w.is_dir():
            raise FileNotFoundError(f"Inner workdir not found: {inner_w}")

        if not inner_w.is_relative_to(outer_w):
            raise ValueError("Subrepo workdir must be relative to superrepo workdir")

        with RepoContext(str(inner_w)) as inner_repo:
            inner_g = _Path(inner_repo.path)
            inner_head_oid = inner_repo.head_commit.oid

        if not inner_g.is_relative_to(outer_w):
            raise ValueError("Subrepo .git dir must be relative to superrepo workdir")

        dot_gitmodules = GitConfig(str(outer_w / ".gitmodules"))
        dot_gitmodules[f"submodule.{inner_w.relative_to(outer_w)}.path"] = inner_w.relative_to(outer_w)
        dot_gitmodules[f"submodule.{inner_w.relative_to(outer_w)}.url"] = remote_url

        if absorb_git_dirs:
            inner_g2 = _Path(self.path, "modules", inner_w.relative_to(outer_w))
            if inner_g2.exists():
                raise FileExistsError(f"Directory already exists: {inner_g2}")
            inner_g2.parent.mkdir(parents=True, exist_ok=True)
            inner_g.rename(inner_g2)
            inner_g = inner_g2

            # TODO: Use Path.relative_to(..., walk_up=True) once we drop support for all versions older than Python 3.13
            submodule_config = GitConfig(str(inner_g / "config"))
            submodule_config["core.worktree"] = _os.path.relpath(inner_w, inner_g2)

            with open(inner_w / ".git", "wt") as submodule_dotgit_file:
                submodule_dotgit_file.write(f"gitdir: {_os.path.relpath(inner_g2, inner_w)}\n")

        # Poor man's workaround for git_submodule_add_to_index (not available in pygit2 yet)
        entry = IndexEntry(inner_w.relative_to(outer_w), inner_head_oid, GIT_FILEMODE_COMMIT)
        self.index.add(entry)

        # While we're here also add .gitmodules
        self.index.add(".gitmodules")

    @staticmethod
    def _sanitize_config_key(key: str | tuple) -> str:
        if type(key) is tuple:
            key = ".".join(key)
        assert type(key) is str
        return key

    def get_config_value(self, key: str | tuple):
        key = self._sanitize_config_key(key)
        try:
            return self.config[key]
        except KeyError:
            return ""

    def set_config_value(self, key: str | tuple, value: str):
        key = self._sanitize_config_key(key)
        if value:
            self.config[key] = value
        else:
            with _contextlib.suppress(KeyError):
                del self.config[key]


class RepoContext:
    def __init__(self, path: str | _Path, flags: int = 0):
        self.repo = Repo(path, flags)

    def __enter__(self) -> Repo:
        return self.repo

    def __exit__(self, exc_type, exc_val, exc_tb):
        # repo.free() is necessary for correct test teardown on Windows
        self.repo.free()
        del self.repo
        self.repo = None


# Remove symbols starting with underscore from public export (for "from porcelain import *")
__all__ = [x for x in dir() if not x.startswith("_")]
