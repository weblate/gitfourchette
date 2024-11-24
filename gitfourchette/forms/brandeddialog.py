# -----------------------------------------------------------------------------
# Copyright (C) 2024 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

from gitfourchette.qt import *
from gitfourchette.toolbox import *


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
