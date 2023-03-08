from gitfourchette import util
from gitfourchette.qt import *
from gitfourchette.widgets.qelidedlabel import QElidedLabel
from typing import Callable


def makeBrandedDialogLayout(
        dialog: QDialog,
        titleText: str,
        subtitleText: str = "",
        multilineSubtitle: bool = False
):
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
    util.tweakWidgetFont(title, 150, bold=True)
    titleLayout.addWidget(title)

    if subtitleText:
        if multilineSubtitle:
            subtitle = QLabel(subtitleText)
            subtitle.setWordWrap(True)
        else:
            subtitle = QElidedLabel(subtitleText, dialog)
        util.tweakWidgetFont(subtitle, relativeSize=90)
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


def convertToBrandedDialog(
        dialog: QDialog,
        promptText: str = "",
        subtitleText: str = "",
        multilineSubtitle: bool = False,
):
    if not promptText:
        promptText = dialog.windowTitle()

    innerContent = QWidget(dialog)
    innerContent.setLayout(dialog.layout())

    gridLayout = makeBrandedDialogLayout(dialog, promptText, subtitleText, multilineSubtitle)
    gridLayout.addWidget(innerContent, 2, 3, 1, 1)


def showTextInputDialog(
        parent: QWidget,
        title: str,
        detailedPrompt: str,
        text: str,
        onAccept: Callable[[str], None] = None,
        okButtonText: str = None,
        validate: Callable[[str], str] = None,
) -> QDialog:

    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setModal(True)

    lineEdit = QLineEdit(dlg)
    dlg.lineEdit = lineEdit
    if text:
        lineEdit.setText(text)
        lineEdit.selectAll()

    buttonBox = QDialogButtonBox(dlg)
    buttonBox.setStandardButtons(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)

    layout = QGridLayout()

    if detailedPrompt:
        detailedPromptLabel = QLabel(detailedPrompt, parent=dlg)
        detailedPromptLabel.setTextFormat(Qt.TextFormat.AutoText)
        detailedPromptLabel.setWordWrap(True)
        layout.addWidget(detailedPromptLabel, 0, 0)

    layout.addWidget(lineEdit, 1, 0)

    validationLabel = None
    if validate:
        validationLabel = QLabel("-validator-")
        layout.addWidget(validationLabel, 1, 1)

    layout.addWidget(buttonBox, 2, 0, 1, -1)

    buttonBox.accepted.connect(dlg.accept)
    buttonBox.rejected.connect(dlg.reject)

    if onAccept:
        dlg.accepted.connect(lambda: onAccept(lineEdit.text()))

    if okButtonText:
        buttonBox.button(QDialogButtonBox.StandardButton.Ok).setText(okButtonText)

    if validate:
        validator = util.GatekeepingValidator(dlg)
        validator.setGatedWidgets(buttonBox.button(QDialogButtonBox.StandardButton.Ok))
        validator.connectInput(lineEdit, validationLabel, validate)
        validator.run()

    makeBrandedDialog(dlg, layout, title)

    # This size isn't guaranteed. But it'll expand the dialog horizontally if the label is shorter.
    dlg.setMinimumWidth(512)

    dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)  # don't leak dialog
    util.setWindowModal(dlg)

    dlg.show()
    dlg.setMinimumHeight(dlg.height())
    dlg.setMaximumHeight(dlg.height())
    return dlg
