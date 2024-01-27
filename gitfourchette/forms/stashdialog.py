from gitfourchette.porcelain import *
from gitfourchette.qt import *
from gitfourchette.toolbox import *
from gitfourchette.forms.brandeddialog import convertToBrandedDialog
from gitfourchette.forms.ui_stashdialog import Ui_StashDialog


class StashDialog(QDialog):
    def __init__(
            self,
            repoStatus: dict[str, int],
            preTicked: list[str],
            parent: QWidget):
        super().__init__(parent)

        self.ui = Ui_StashDialog()
        self.ui.setupUi(self)

        self.ui.indexAndWtWarning.setVisible(False)

        for l in (self.ui.willBackUpChangesLabel,
                  self.ui.willRemoveChangesLabel,
                  self.ui.willKeepChangesLabel,
                  self.ui.indexAndWtWarning):
            tweakWidgetFont(l, 95)

        okButton = self.ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok)

        self.ui.cleanupCheckBox.clicked.connect(lambda clean: okButton.setText(
            self.tr("Stash then Remove Changes") if clean else self.tr("Stash and Keep Changes")))

        self.ui.fileList.setUniformItemSizes(True)
        scrollTo = None
        for filePath, fileStatus in repoStatus.items():
            if (fileStatus & FileStatus_INDEX_MASK) and (fileStatus & FileStatus_WT_MASK):
                self.ui.indexAndWtWarning.setVisible(True)

            listItem = QListWidgetItem(filePath, self.ui.fileList)
            listItem.setSizeHint(QSize(100, 16))
            listItem.setData(Qt.ItemDataRole.UserRole, filePath)
            tweakWidgetFont(listItem, 95)
            if not preTicked or filePath in preTicked:
                listItem.setCheckState(Qt.CheckState.Checked)
                if not scrollTo:
                   scrollTo = listItem
            else:
                listItem.setCheckState(Qt.CheckState.Unchecked)
            # listItem.setIcon(stockIcon("status_m"))
            self.ui.fileList.addItem(listItem)

        # Prime checkbox signal connections
        self.ui.cleanupCheckBox.click()
        self.ui.cleanupCheckBox.click()

        convertToBrandedDialog(self)

        # Make sure at least one ticked item is visible
        if scrollTo:
            self.ui.fileList.scrollToItem(scrollTo, hint=QAbstractItemView.ScrollHint.EnsureVisible)

    def tickedPaths(self) -> list[str]:
        paths = []

        for i in range(self.ui.fileList.count()):
            listItem = self.ui.fileList.item(i)
            if listItem.checkState() != Qt.CheckState.Unchecked:
                path = listItem.data(Qt.ItemDataRole.UserRole)
                paths.append(path)

        return paths
