from allgit import *
import html


class FileListEntry:
    path: str
    patch: Patch
    icon: str
    tooltip: str

    @classmethod
    def fromDelta(cls, delta: DiffDelta, patch: Patch):
        entry = cls()
        entry.patch = patch
        entry.icon = delta.status_char()
        assert delta.new_file
        assert delta.new_file.path
        entry.path = delta.new_file.path
        entry.tooltip = F"""
                <b>from:</b> {html.escape(delta.old_file.path)} ({delta.old_file.mode:o})
                <br><b>to:</b> {html.escape(delta.new_file.path)} ({delta.new_file.mode:o})
                <br><b>operation:</b> {delta.status_char()}
                <br><b>similarity:</b> {delta.similarity} (valid for R only)
                """
        return entry

    @classmethod
    def Untracked(cls, path: str):
        entry = cls()
        entry.diff = None
        entry.path = path
        entry.icon = 'A'
        entry.tooltip = entry.path + '\n(untracked file)'
        return entry

