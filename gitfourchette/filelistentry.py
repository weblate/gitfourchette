import git


class FileListEntry:
    path: str
    diff: git.Diff
    icon: str
    tooltip: str

    @classmethod
    def Tracked(cls, diff: git.Diff):
        entry = cls()
        entry.diff = diff
        entry.icon = diff.change_type
        # Prefer b_path; if it's a deletion, a_path may not be available
        entry.path = diff.b_path or diff.a_path
        entry.tooltip = str(diff)
        return entry

    @classmethod
    def Untracked(cls, path: str):
        entry = cls()
        entry.diff = None
        entry.path = path
        entry.icon = 'A'
        entry.tooltip = entry.path + '\n(untracked file)'
        return entry

