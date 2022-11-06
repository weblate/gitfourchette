from gitfourchette.qt import *
from gitfourchette.util import tweakWidgetFont
from gitfourchette.widgets.qelidedlabel import QElidedLabel
from typing import Callable


def makeBrandedDialogLayout(dialog, titleText, subtitleText=""):
    gridLayout = QGridLayout(dialog)

    iconLabel = QLabel(dialog)
    iconLabel.setMaximumSize(QSize(56, 56))
    iconLabel.setPixmap(QPixmap("assets:gitfourchette.png"))
    iconLabel.setScaledContents(True)
    iconLabel.setMargin(8)

    horizontalSpacer = QSpacerItem(0, 1, QSizePolicy.Fixed, QSizePolicy.Minimum)

    titleLayout = QVBoxLayout()
    titleLayout.setSpacing(0)
    titleLayout.setContentsMargins(0, 0, 0, 0)
    title = QLabel(titleText, dialog)
    title.setTextFormat(Qt.TextFormat.RichText)
    tweakWidgetFont(title, 150, bold=True)
    titleLayout.addWidget(title)

    if subtitleText:
        subtitle = QElidedLabel(subtitleText, dialog)
        tweakWidgetFont(subtitle, relativeSize=90)
        titleLayout.addWidget(subtitle)
        title.setAlignment(Qt.AlignmentFlag.AlignBottom)
        subtitle.setAlignment(Qt.AlignmentFlag.AlignTop)

    gridLayout.addWidget(iconLabel, 1, 0, 1, 1)
    gridLayout.addItem(horizontalSpacer, 1, 1, 1, 1)
    gridLayout.addLayout(titleLayout, 1, 3, 1, 1)

    return gridLayout


def makeBrandedDialog(dialog, innerLayout, promptText, subtitleText: str = ""):
    gridLayout = makeBrandedDialogLayout(dialog, promptText, subtitleText)
    gridLayout.addLayout(innerLayout, 2, 3, 1, 1)


def convertToBrandedDialog(dialog: QDialog, promptText: str = "", subtitleText: str = ""):
    if not promptText:
        promptText = dialog.windowTitle()

    innerContent = QWidget(dialog)
    innerContent.setLayout(dialog.layout())

    gridLayout = makeBrandedDialogLayout(dialog, promptText, subtitleText)
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

    buttonBox = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, parent=dlg)

    layout = QVBoxLayout()
    if detailedPrompt:
        detailedPromptLabel = QLabel(detailedPrompt, parent=dlg)
        detailedPromptLabel.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(detailedPromptLabel)
    layout.addWidget(lineEdit)
    layout.addWidget(buttonBox)

    buttonBox.accepted.connect(dlg.accepted)
    buttonBox.rejected.connect(dlg.rejected)

    if onAccept:
        dlg.accepted.connect(lambda: onAccept(lineEdit.text()))
        dlg.accepted.connect(dlg.close)
    dlg.rejected.connect(dlg.close)

    if okButtonText:
        buttonBox.button(QDialogButtonBox.StandardButton.Ok).setText(okButtonText)

    makeBrandedDialog(dlg, layout, title)

    # This size isn't guaranteed. But it'll expand the dialog horizontally if the label is shorter.
    dlg.resize(512, 128)
    dlg.setMaximumHeight(dlg.height())

    dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)  # don't leak dialog
    dlg.setWindowModality(Qt.WindowModality.WindowModal)

    dlg.show()
    dlg.setMaximumHeight(dlg.height())
    return dlg
