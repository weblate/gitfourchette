import pytest

from . import reposcenario
from .util import *
from gitfourchette.nav import NavLocator
from gitfourchette.sidebar.sidebarmodel import EItem


def testExportPatchFromWorkdir(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    writeFile(f"{wd}/master.txt", "some changes\n")
    writeFile(f"{wd}/untracked-file.txt", "hello\n")
    rw = mainWindow.openRepo(wd)
    assert qlvGetRowData(rw.dirtyFiles) == ["master.txt", "untracked-file.txt"]

    node = next(rw.sidebar.findNodesByKind(EItem.UncommittedChanges))
    triggerMenuAction(rw.sidebar.makeNodeMenu(node), r"export.+patch")
    acceptQFileDialog(rw, "export.+patch", f"{tempDir.name}/workdir.patch")

    triggerMenuAction(mainWindow.menuBar(), "file/reverse patch")
    acceptQFileDialog(rw, "import patch.+reverse", f"{tempDir.name}/workdir.patch")
    acceptQMessageBox(rw, "patch.+can be applied")
    assert qlvGetRowData(rw.dirtyFiles) == []

    triggerMenuAction(mainWindow.menuBar(), "file/reverse patch")
    acceptQFileDialog(rw, "import patch.+reverse", f"{tempDir.name}/workdir.patch")
    acceptQMessageBox(rw, "failed.+patch")

    triggerMenuAction(mainWindow.menuBar(), "file/apply patch")
    acceptQFileDialog(rw, "import patch", f"{tempDir.name}/workdir.patch")
    acceptQMessageBox(rw, "patch.+can be applied")
    assert qlvGetRowData(rw.dirtyFiles) == ["master.txt", "untracked-file.txt"]


def testExportPatchFromEmptyWorkdir(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)

    node = next(rw.sidebar.findNodesByKind(EItem.UncommittedChanges))
    triggerMenuAction(rw.sidebar.makeNodeMenu(node), r"export.+patch")
    acceptQMessageBox(rw, "patch is empty")


def testExportPatchFromCommit(tempDir, mainWindow):
    oid = Oid(hex="c9ed7bf12c73de26422b7c5a44d74cfce5a8993b")
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)

    rw.jump(NavLocator.inCommit(oid))
    menu = rw.graphView.makeContextMenu()
    triggerMenuAction(menu, r"export.+patch")
    acceptQFileDialog(rw, "export.+patch", f"{tempDir.name}/foo.patch")

    triggerMenuAction(mainWindow.menuBar(), "file/reverse patch")
    acceptQFileDialog(rw, "import patch.+reverse", f"{tempDir.name}/foo.patch")
    acceptQMessageBox(rw, "patch.+can be applied")
    assert rw.navLocator.context.isWorkdir()
    assert qlvGetRowData(rw.dirtyFiles) == ["c/c2-2.txt"]

    triggerMenuAction(mainWindow.menuBar(), "file/apply patch")
    acceptQFileDialog(rw, "import.+patch", f"{tempDir.name}/foo.patch")
    acceptQMessageBox(rw, "patch.+can be applied")
    assert qlvGetRowData(rw.dirtyFiles) == []


def testExportPatchFromStash(tempDir, mainWindow):
    wd = unpackRepo(tempDir)
    reposcenario.stashedChange(wd)
    rw = mainWindow.openRepo(wd)

    assert 1 == len(list(rw.sidebar.findNodesByKind(EItem.Stash)))
    node = rw.sidebar.findNodeByRef("stash@{0}")
    menu = rw.sidebar.makeNodeMenu(node)
    triggerMenuAction(menu, r"export.+patch")
    acceptQFileDialog(rw, "export stash.+patch", f"{tempDir.name}/foo.patch")

    triggerMenuAction(mainWindow.menuBar(), "file/apply patch")
    acceptQFileDialog(rw, "import patch", f"{tempDir.name}/foo.patch")
    acceptQMessageBox(rw, "patch.+can be applied")
    assert qlvGetRowData(rw.dirtyFiles) == ["a/a1.txt"]

    triggerMenuAction(mainWindow.menuBar(), "file/reverse patch")
    acceptQFileDialog(rw, "import patch.+reverse", f"{tempDir.name}/foo.patch")
    acceptQMessageBox(rw, "patch.+can be applied")
    assert qlvGetRowData(rw.dirtyFiles) == []


@pytest.mark.parametrize("commitHex,path", [
    ("c9ed7bf12c73de26422b7c5a44d74cfce5a8993b", "c/c2-2.txt"),
    ("7f822839a2fe9760f386cbbbcb3f92c5fe81def7", "b/b2.txt"),
    ("f73b95671f326616d66b2afb3bdfcdbbce110b44", "a/a1"),
])
def testExportPatchFromFileList(tempDir, mainWindow, commitHex, path):
    wd = unpackRepo(tempDir)
    rw = mainWindow.openRepo(wd)

    rw.jump(NavLocator.inCommit(Oid(hex=commitHex), path))
    rw.committedFiles.savePatchAs()
    acceptQFileDialog(rw, "export patch", f"{tempDir.name}/foo.patch")

    triggerMenuAction(mainWindow.menuBar(), "file/reverse patch")
    acceptQFileDialog(rw, "import patch.+reverse", f"{tempDir.name}/foo.patch")
    acceptQMessageBox(rw, "patch.+can be applied")
