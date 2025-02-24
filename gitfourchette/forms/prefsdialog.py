# -----------------------------------------------------------------------------
# Copyright (C) 2024 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

import logging
from typing import Any

from gitfourchette.porcelain import *
from gitfourchette.qt import *
from gitfourchette.settings import (
    SHORT_DATE_PRESETS,
    prefs,
    qtIsNativeMacosStyle,
)
from gitfourchette.toolbox import *
from gitfourchette.toolcommands import ToolCommands
from gitfourchette.trtables import TrTables

logger = logging.getLogger(__name__)

SAMPLE_SIGNATURE = Signature("Jean-Michel Tartempion", "jm.tarte@example.com", 0, 0)
SAMPLE_FILE_PATH = "spam/.ham/eggs/hello.c"


def _boxWidget(layoutType, *controls):
    w = QWidget()
    layout: QBoxLayout = layoutType(w)
    layout.setSpacing(0)
    layout.setContentsMargins(0, 0, 0, 0)
    for control in controls:
        layout.addWidget(control)
    return w


def vBoxWidget(*controls):
    return _boxWidget(QVBoxLayout, *controls)


def hBoxWidget(*controls):
    return _boxWidget(QHBoxLayout, *controls)


class PrefsDialog(QDialog):
    lastOpenTab = 0

    prefDiff: dict[str, Any]
    "Delta to on-disk preferences."

    @benchmark
    def __init__(self, parent: QWidget, focusOn: str = ""):
        super().__init__(parent)

        self.setObjectName("PrefsDialog")
        self.setWindowTitle(translate("Prefs", "{app} Settings").format(app=qAppName()))

        self.prefDiff = {}

        # Prepare main widgets & layout
        tabWidget = QTabWidget(self)
        self.tabs = tabWidget

        buttonBox = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(tabWidget)
        layout.addWidget(buttonBox)

        # Make tabs vertical if possible (macOS style: too messy)
        if qtIsNativeMacosStyle():
            tabWidget.setTabPosition(QTabWidget.TabPosition.North)
        else:
            # Pass a string to the proxy's ctor, NOT QApplication.style() as this would transfer the ownership
            # of the style to the proxy!!!
            proxyStyle = QTabBarStyleNoRotatedText(prefs.qtStyle)
            tabWidget.setStyle(proxyStyle)
            tabWidget.setTabPosition(QTabWidget.TabPosition.West if self.isLeftToRight() else QTabWidget.TabPosition.East)

        category = "general"
        categoryForms: dict[str, QFormLayout] = {}
        skipKeys = self.getHiddenSettingKeys()

        for prefKey in prefs.__dict__:
            # Switch category
            if prefKey.startswith("_category_"):
                category = prefKey.removeprefix("_category_")
                continue

            # Skip irrelevant settings
            if prefKey in skipKeys or prefKey.startswith("_") or category == "hidden":
                continue

            # Get the value of this setting
            prefValue = prefs.__dict__[prefKey]

            # Get caption and suffix
            suffix = ""
            caption = TrTables.prefKey(prefKey)
            if "#" in caption:
                caption, suffix = caption.split("#")
                caption = caption.rstrip()
                suffix = suffix.lstrip()

            # Get a QFormLayout for this setting's category
            try:
                # Get form for existing category
                form = categoryForms[category]
            except KeyError:
                # Create form in new tab for this category
                formContainer = QWidget(self)
                form = QFormLayout(formContainer)
                form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
                categoryForms[category] = form
                tabName = TrTables.prefKey(category)
                tabWidget.addTab(formContainer, tabName)

                headerText = TrTables.prefKey(f"{category}_HEADER")
                if headerText != f"{category}_HEADER":
                    headerText = headerText.format(app=qAppName())
                    explainer = QLabel(headerText)
                    explainer.setWordWrap(True)
                    explainer.setTextFormat(Qt.TextFormat.RichText)
                    tweakWidgetFont(explainer, 88)
                    form.addRow(explainer)

            # Make the actual control widget
            control = self.makeControlWidget(prefKey, prefValue, caption)
            control.setObjectName(f"prefctl_{prefKey}")  # Name the control so that unit tests can find it
            rowWidgets = [control]

            # Tack an extra QLabel to the end if there's a suffix
            if suffix:
                rowWidgets.append(QLabel(suffix))

            # Any help text? Then make a help button for it & set tooltip text on the main control
            toolTip = TrTables.prefKeyNoDefault(prefKey + "_help")
            if toolTip:
                toolTip = toolTip.format(app=qAppName())
                control.setToolTip(toolTip)
                hintButton = QHintButton(self, toolTip)
                hintButton.setMaximumHeight(2 + hintButton.fontMetrics().height())
                rowWidgets.append(hintButton)

            # Gather what to add to the form as a single item.
            # If we have more than a single widget to add to the form, lay them out in a row.
            if len(rowWidgets) == 1:
                formField = control
                assert rowWidgets[0] is control
            else:
                rowLayout = QHBoxLayout()
                for w in rowWidgets:
                    rowLayout.addWidget(w)
                if control.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Minimum:
                    # Stick help button to right edge of non-expanding widget
                    rowLayout.addStretch()
                formField = rowLayout

            # Add `formField` to the form layout, with a leading caption if any
            if not caption or type(control) is QCheckBox:
                # No caption, make field span entire row
                form.addRow(formField)
            else:
                # There's a leading caption, so add it as the label in the row
                caption += tr(":", "generic caption suffix")
                captionLabel = QLabel(caption)
                captionLabel.setBuddy(control)
                if toolTip:
                    captionLabel.setToolTip(toolTip)
                form.addRow(captionLabel, formField)

            # If the current key matches the setting we want to focus on, bring this tab to the foreground
            if focusOn == prefKey:
                tabWidget.setCurrentWidget(form.parentWidget())
                control.setFocus()

        if not focusOn:
            # Restore last open tab
            tabWidget.setCurrentIndex(PrefsDialog.lastOpenTab)
            buttonBox.button(QDialogButtonBox.StandardButton.Ok).setFocus()
        else:
            # Save this tab if we close the dialog without changing tabs
            self.saveLastOpenTab(tabWidget.currentIndex())

        # Remember which tab we've last clicked on for next time we open the dialog
        tabWidget.currentChanged.connect(PrefsDialog.saveLastOpenTab)

        self.setModal(True)

    def assign(self, k, v):
        if prefs.__dict__[k] == v:
            if k in self.prefDiff:
                del self.prefDiff[k]
        else:
            self.prefDiff[k] = v
        logger.debug(f"Assign {k} {v} ({type(v)})")

    def getMostRecentValue(self, k):
        if k in self.prefDiff:
            return self.prefDiff[k]
        elif k in prefs.__dict__:
            return prefs.__dict__[k]
        else:
            return None

    @staticmethod
    def saveLastOpenTab(i):
        PrefsDialog.lastOpenTab = i

    def getHiddenSettingKeys(self) -> set[str]:
        skipKeys = set()

        # Prevent hiding menubar on macOS
        if MACOS:
            skipKeys.add("showMenuBar")

        # If app distribution is frozen, don't expose Qt binding setting
        if APP_FREEZE_QT:
            skipKeys.add("forceQtApi")

        return skipKeys

    def makeControlWidget(self, key: str, value, caption: str) -> QWidget:
        valueType = type(value)

        if key == "language":
            return self.languageControl(key, value)
        elif key == "qtStyle":
            return self.qtStyleControl(key, value)
        elif key == "font":
            return self.fontControl(key)
        elif key == "shortTimeFormat":
            return self.dateFormatControl(key, value, SHORT_DATE_PRESETS)
        elif key == "pathDisplayStyle":
            return self.enumControl(key, value, valueType, previewCallback=lambda v: abbreviatePath(SAMPLE_FILE_PATH, v))
        elif key == "authorDisplayStyle":
            return self.enumControl(key, value, valueType, previewCallback=lambda v: abbreviatePerson(SAMPLE_SIGNATURE, v))
        elif key == "shortHashChars":
            return self.boundedIntControl(key, value, 4, 40)
        elif key == "maxRecentRepos":
            return self.boundedIntControl(key, value, 0, 50)
        elif key == "contextLines":  # staging/discarding individual lines is flaky with 0 context lines
            return self.boundedIntControl(key, value, 1, 32)
        elif key == "tabSpaces":
            return self.boundedIntControl(key, value, 1, 16)
        elif key == "maxCommits":
            control = self.boundedIntControl(key, value, 0, 999_999_999, 1000)
            control.setSpecialValueText("\u221E")  # infinity
            return control
        elif key == "renderSvg":
            return self.boolComboBoxControl(key, value, falseName=self.tr("Text"), trueName=self.tr("Image"))
        elif key == "externalEditor":
            return self.strControlWithPresets(key, value, ToolCommands.EditorPresets, leaveBlankHint=True)
        elif key == "externalDiff":
            return self.strControlWithPresets(
                key, value, ToolCommands.DiffPresets,
                validate=lambda cmd: ToolCommands.checkCommand(cmd, "$L", "$R"))
        elif key == "externalMerge":
            return self.strControlWithPresets(
                key, value, ToolCommands.MergePresets,
                validate=lambda cmd: ToolCommands.checkCommand(cmd, "$L", "$R", "$B", "$M"))
        elif key in ["largeFileThresholdKB", "imageFileThresholdKB", "maxTrashFileKB"]:
            control = self.boundedIntControl(key, value, 0, 999_999)
            control.setSpecialValueText("\u221E")  # infinity
            return control
        elif issubclass(valueType, enum.Enum):
            return self.enumControl(key, value, type(value))
        elif valueType is int:
            return self.intControl(key, value)
        elif valueType is bool:
            trueText = TrTables.prefKeyNoDefault(key + "_true")
            falseText = TrTables.prefKeyNoDefault(key + "_false")
            if trueText or falseText:
                return self.boolComboBoxControl(key, value, trueName=trueText, falseName=falseText)
            else:
                control = QCheckBox(caption, self)
                control.setCheckState(Qt.CheckState.Checked if value else Qt.CheckState.Unchecked)
                control.stateChanged.connect(lambda v, k=key, c=control: self.assign(k, c.isChecked()))  # PySide6: "v==Qt.CheckState.Checked" doesn't work anymore?
                return control
        else:
            raise NotImplementedError(f"Write pref widget for {key}")

    def languageControl(self, prefKey: str, prefValue: str):
        defaultCaption = translate("Prefs", "System default", "system default language setting")
        control = QComboBox(self)
        control.addItem(defaultCaption, userData="")
        if not prefValue:
            control.setCurrentIndex(0)
        control.insertSeparator(1)
        langDir = QDir("assets:lang", "gitfourchette_*.qm")
        languages = [qmFile.removeprefix("gitfourchette_").removesuffix(".qm") for qmFile in langDir.entryList()]
        for enumMember in languages:
            lang = QLocale(enumMember)
            control.addItem(lang.nativeLanguageName().title(), enumMember)
            if prefValue == enumMember:
                control.setCurrentIndex(control.count() - 1)

        control.activated.connect(lambda index: self.assign(prefKey, control.currentData(Qt.ItemDataRole.UserRole)))
        return control

    def fontControl(self, prefKey: str):
        def currentFont():
            fontString = self.getMostRecentValue(prefKey)
            if fontString:
                font = QFont()
                font.fromString(fontString)
            else:
                font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
            return font

        def resetFont():
            self.assign(prefKey, "")
            refreshFontButton()

        def onFontSelected(newFont: QFont):
            self.assign(prefKey, newFont.toString())
            refreshFontButton()

        def pickFont():
            qfd = QFontDialog(currentFont(), parent=self)
            qfd.fontSelected.connect(onFontSelected)
            qfd.setModal(True)
            qfd.show()

        fontButton = QPushButton(translate("Prefs", "Font"))
        fontButton.setObjectName("PickFontButton")
        fontButton.clicked.connect(lambda e: pickFont())
        fontButton.setMinimumWidth(256)
        fontButton.setMaximumWidth(256)
        fontButton.setMaximumHeight(128)

        resetButton = QToolButton(self)
        resetButton.setObjectName("ResetFontButton")
        resetButton.setText(translate("Prefs", "Reset", "reset font"))
        resetButton.clicked.connect(lambda: resetFont())

        def refreshFontButton():
            font = currentFont()
            if not self.getMostRecentValue(prefKey):
                resetButton.setVisible(False)
                caption = translate("Prefs", "Default", "as in Default Font")
                caption += f" ({font.family()} {font.pointSize()})"
                fontButton.setText(caption)
            else:
                resetButton.setVisible(True)
                fontButton.setText(F"{font.family()} {font.pointSize()}")
            fontButton.setFont(font)

        refreshFontButton()

        return hBoxWidget(fontButton, resetButton)

    def strControlWithPresets(self, prefKey, prefValue, presets, leaveBlankHint=False, validate=None):
        control = QComboBoxWithPreview(self)
        control.setEditable(True)

        for k in presets:
            preview = presets[k]
            if not preview and leaveBlankHint:
                preview = "- " + translate("Prefs", "leave blank", "hint user to leave the field blank") + " -"
            control.addItemWithPreview(k, presets[k], preview)
            if prefValue == presets[k]:
                control.setCurrentIndex(control.count()-1)

        if leaveBlankHint:
            control.lineEdit().setPlaceholderText(translate("Prefs", "Leave blank for system default."))

        control.setEditText(prefValue)
        control.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred))

        control.editTextChanged.connect(lambda text: self.assign(prefKey, text))

        if validate:
            validator = ValidatorMultiplexer(self)
            validator.connectInput(control.lineEdit(), validate, mustBeValid=False)
            validator.run()

        return control

    def intControl(self, prefKey, prefValue):
        control = QLineEdit(str(prefValue), self)
        control.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        control.setValidator(QIntValidator())
        control.textEdited.connect(lambda v, k=prefKey: self.assign(k, int(v) if v else 0))
        return control

    def boundedIntControl(self, prefKey, prefValue, minValue, maxValue, step=1):
        control = QSpinBox(self)
        control.setMinimum(minValue)
        control.setMaximum(maxValue)
        control.setValue(prefValue)
        control.setSingleStep(step)
        control.setGroupSeparatorShown(True)
        control.setAlignment(Qt.AlignmentFlag.AlignRight)
        control.setStepType(QSpinBox.StepType.AdaptiveDecimalStepType)
        control.valueChanged.connect(lambda v, k=prefKey: self.assign(k, v))
        return control

    def boolComboBoxControl(self, prefKey: str, prefValue: bool, falseName: str, trueName: str) -> QComboBox:
        control = QComboBox(self)
        control.addItem(trueName)  # index 0 --> True
        control.addItem(falseName)  # index 1 --> False
        control.setCurrentIndex(int(not prefValue))
        control.activated.connect(lambda index: self.assign(prefKey, index == 0))
        return control

    def enumControl(self, prefKey, prefValue, enumType, previewCallback=None):
        if previewCallback:
            control = QComboBoxWithPreview(self)
        else:
            control = QComboBox(self)

        for enumMember in enumType:
            # PySide2/PySide6 demotes StrEnum to str when stored with QComboBox.setItemData().
            # Wrap the value in a tuple to preserve the type. (PyQt5 & PyQt6 do the right thing here)
            data = (enumMember,)
            name = TrTables.prefKey(enumMember.name)

            if previewCallback:
                control.addItemWithPreview(name, data, previewCallback(enumMember))
            else:
                control.addItem(name, data)
            if prefValue == enumMember:
                control.setCurrentIndex(control.count() - 1)

        control.activated.connect(lambda i: self.assign(prefKey, control.itemData(i)[0]))  # unpack the tuple!

        return control

    def qtStyleControl(self, prefKey, prefValue):
        defaultCaption = translate("Prefs", "System default", "default Qt style setting")
        control = QComboBox(self)
        control.addItem(defaultCaption, userData="")
        if not prefValue:
            control.setCurrentIndex(0)
        control.insertSeparator(1)
        for availableStyle in QStyleFactory.keys():
            control.addItem(availableStyle, userData=availableStyle)
            if prefValue == availableStyle:
                control.setCurrentIndex(control.count() - 1)

        def onPickStyle(index):
            styleName = control.itemData(index, Qt.ItemDataRole.UserRole)
            self.assign(prefKey, styleName)

        control.activated.connect(onPickStyle)
        return control

    def dateFormatControl(self, prefKey, prefValue, presets):
        currentDate = QDateTime.currentDateTime()
        sampleDate = QDateTime(QDate(currentDate.date().year(), 1, 30), QTime(9, 45))
        bogusTime = "Wednesday, December 99, 9999 99:99:99 AM"

        def genPreview(f):
            return QLocale().toString(sampleDate, f)

        def onEditTextChanged(text):
            preview.setText(genPreview(text))
            self.assign(prefKey, text)

        preview = QLabel(bogusTime)
        preview.setEnabled(False)
        preview.setMaximumWidth(preview.fontMetrics().horizontalAdvance(bogusTime))

        control = QComboBoxWithPreview(self)
        control.setEditable(True)
        for presetName, presetFormat in presets.items():
            control.addItemWithPreview(presetName, presetFormat, genPreview(presetFormat))
            if prefValue == presetFormat:
                control.setCurrentIndex(control.count()-1)
        control.editTextChanged.connect(onEditTextChanged)
        control.setMinimumWidth(200)
        control.setEditText(prefValue)

        return vBoxWidget(control, preview)
