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
        self.ui.keepCheckBox.setToolTip("<p>" + self.ui.keepCheckBox.toolTip())
        self.ui.indexAndWtWarning.setVisible(False)

        for label in (self.ui.willStashLabel, self.ui.indexAndWtWarning):
            tweakWidgetFont(label, 90)

        okButton = self.ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok)

        buttonCaptions = [self.tr("Stash && Reset Changes"), self.tr("Stash && Keep Changes")]
        helpCaptions = [
            self.tr("&Include these files in the stash, then reset them to their unmodified state:"),
            self.tr("&Include these files in the stash:")]
        self.ui.keepCheckBox.clicked.connect(lambda keep: okButton.setText(buttonCaptions[keep]))
        self.ui.keepCheckBox.clicked.connect(lambda keep: self.ui.willStashLabel.setText(helpCaptions[keep]))

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
        self.ui.keepCheckBox.click()
        self.ui.keepCheckBox.click()

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
