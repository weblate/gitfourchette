from gitfourchette.qt import *
from gitfourchette.toolbox import *
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
    iconLabel.setPixmap(QPixmap("assets:icons/gitfourchette"))
    iconLabel.setScaledContents(True)
    iconLabel.setMargin(8)

    horizontalSpacer = QSpacerItem(0, 1, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)

    titleLayout = QVBoxLayout()
    titleLayout.setSpacing(0)
    titleLayout.setContentsMargins(0, 0, 0, 0)
    title = QLabel(titleText, dialog)
    title.setTextFormat(Qt.TextFormat.RichText)
    title.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
    tweakWidgetFont(title, 150, bold=True)
    titleLayout.addWidget(title)

    if subtitleText:
        title.setAlignment(Qt.AlignmentFlag.AlignBottom)
        subtitleWidgets = []

        if multilineSubtitle:
            subtitle = QLabel(subtitleText)
            subtitle.setWordWrap(True)
            subtitleWidgets.append(subtitle)
        else:
            for line in subtitleText.splitlines():
                subtitleWidgets.append(QElidedLabel(line, dialog))

        for subtitle in subtitleWidgets:
            subtitle.setAlignment(Qt.AlignmentFlag.AlignTop)
            tweakWidgetFont(subtitle, relativeSize=90)
            titleLayout.addWidget(subtitle)

    gridLayout.addWidget(iconLabel, 0, 0, 1, 1)
    gridLayout.addItem(horizontalSpacer, 0, 1, 1, 1)
    gridLayout.addLayout(titleLayout, 0, 3, 1, 1)

    if subtitleText:
        breather = QSpacerItem(0, 8, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        gridLayout.addItem(breather, 1, 0)

    return gridLayout


def makeBrandedDialog(dialog, innerLayout, promptText: str = "", subtitleText: str = ""):
    if not promptText:
        promptText = escape(dialog.windowTitle())

    gridLayout = makeBrandedDialogLayout(dialog, promptText, subtitleText)
    gridLayout.addLayout(innerLayout, 2, 3, 1, 1)


def convertToBrandedDialog(
        dialog: QDialog,
        promptText: str = "",
        subtitleText: str = "",
        multilineSubtitle: bool = False,
):
    if not promptText:
        promptText = escape(dialog.windowTitle())

    innerContent = QWidget(dialog)
    innerContent.setLayout(dialog.layout())
    innerContent.layout().setContentsMargins(0, 0, 0, 0)

    gridLayout = makeBrandedDialogLayout(dialog, promptText, subtitleText, multilineSubtitle)
    gridLayout.addWidget(innerContent, 2, 3, 1, 1)


def showTextInputDialog(
        parent: QWidget,
        title: str,
        detailedPrompt: str,
        text: str = "",
        onAccept: Callable[[str], None] = None,
        okButtonText: str = None,
        validate: Callable[[str], str] = None,
        deleteOnClose: bool = True,
        placeholderText: str = "",
        subtitleText: str = "",
) -> QDialog:

    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setModal(True)

    lineEdit = QLineEdit(dlg)
    dlg.lineEdit = lineEdit
    if text:
        lineEdit.setText(text)
        lineEdit.selectAll()
    lineEdit.setPlaceholderText(placeholderText)

    buttonBox = QDialogButtonBox(dlg)
    buttonBox.setStandardButtons(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)

    layout = QGridLayout()

    if detailedPrompt:
        detailedPromptLabel = QLabel(detailedPrompt, parent=dlg)
        detailedPromptLabel.setTextFormat(Qt.TextFormat.AutoText)
        detailedPromptLabel.setWordWrap(True)
        layout.addWidget(detailedPromptLabel, 0, 0)

    layout.addWidget(lineEdit, 1, 0)

    layout.addWidget(buttonBox, 2, 0, 1, -1)

    buttonBox.accepted.connect(dlg.accept)
    buttonBox.rejected.connect(dlg.reject)

    if onAccept:
        dlg.accepted.connect(lambda: onAccept(lineEdit.text()))

    if okButtonText:
        buttonBox.button(QDialogButtonBox.StandardButton.Ok).setText(okButtonText)

    if validate:
        validator = ValidatorMultiplexer(dlg)
        validator.setGatedWidgets(buttonBox.button(QDialogButtonBox.StandardButton.Ok))
        validator.connectInput(lineEdit, validate)
        validator.run()

    makeBrandedDialog(dlg, layout, subtitleText=subtitleText)

    # This size isn't guaranteed. But it'll expand the dialog horizontally if the label is shorter.
    dlg.setMinimumWidth(512)

    if deleteOnClose:
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

    dlg.setWindowModality(Qt.WindowModality.WindowModal)

    dlg.buttonBox = buttonBox

    lineEdit.setFocus()

    dlg.show()
    dlg.setMinimumHeight(dlg.height())
    dlg.setMaximumHeight(dlg.height())
    return dlg
