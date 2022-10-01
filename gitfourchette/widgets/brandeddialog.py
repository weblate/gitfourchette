from gitfourchette.qt import *
from typing import Callable


def makeBrandedDialogLayout(dialog, promptText):
    gridLayout = QGridLayout(dialog)

    iconLabel = QLabel(dialog)
    iconLabel.setMaximumSize(QSize(56, 56))
    iconLabel.setPixmap(QPixmap(":/gitfourchette.png"))
    iconLabel.setScaledContents(True)
    iconLabel.setMargin(8)

    horizontalSpacer = QSpacerItem(0, 1, QSizePolicy.Fixed, QSizePolicy.Minimum)

    prompt = QLabel(dialog)
    prompt.setText(promptText)
    font: QFont = prompt.font()
    font.setPointSize(font.pointSize() * 150 // 100)
    font.setBold(True)
    prompt.setFont(font)

    gridLayout.addWidget(iconLabel, 1, 0, 1, 1)
    gridLayout.addItem(horizontalSpacer, 1, 1, 1, 1)
    gridLayout.addWidget(prompt, 1, 3, 1, 1)

    return gridLayout


def makeBrandedDialog(dialog, innerLayout, promptText):
    gridLayout = makeBrandedDialogLayout(dialog, promptText)
    gridLayout.addLayout(innerLayout, 2, 3, 1, 1)


def convertToBrandedDialog(dialog: QDialog, promptText: str = ""):
    if not promptText:
        promptText = dialog.windowTitle()

    innerContent = QWidget(dialog)
    innerContent.setLayout(dialog.layout())

    gridLayout = makeBrandedDialogLayout(dialog, promptText)
    gridLayout.addWidget(innerContent, 2, 3, 1, 1)


def showTextInputDialog(
        parent: QWidget,
        title: str,
        detailedPrompt: str,
        text: str,
        onAccept: Callable[[str], None],
        okButtonText: str = None
) -> QInputDialog:

    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setModal(True)

    lineEdit = QLineEdit(dlg)
    if text:
        lineEdit.setText(text)
        lineEdit.selectAll()

    buttonBox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=dlg)

    layout = QVBoxLayout()
    if detailedPrompt:
        layout.addWidget(QLabel(detailedPrompt, parent=dlg))
    layout.addWidget(lineEdit)
    layout.addWidget(buttonBox)

    buttonBox.accepted.connect(dlg.accepted)
    buttonBox.rejected.connect(dlg.rejected)

    if onAccept:
        dlg.accepted.connect(lambda: onAccept(lineEdit.text()))
        dlg.accepted.connect(dlg.close)
    dlg.rejected.connect(dlg.close)

    if okButtonText:
        buttonBox.button(QDialogButtonBox.Ok).setText(okButtonText)

    makeBrandedDialog(dlg, layout, title)

    # This size isn't guaranteed. But it'll expand the dialog horizontally if the label is shorter.
    dlg.resize(512, 128)
    dlg.setMaximumHeight(dlg.height())

    dlg.setAttribute(Qt.WA_DeleteOnClose)  # don't leak dialog
    dlg.setWindowModality(Qt.WindowModal)

    dlg.show()
    dlg.setMaximumHeight(dlg.height())
    return dlg
