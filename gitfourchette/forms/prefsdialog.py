import enum
import logging

from gitfourchette.porcelain import *
from gitfourchette.qt import *
from gitfourchette.settings import (
    DIFF_TOOL_PRESETS,
    EDITOR_TOOL_PRESETS,
    LANGUAGES,
    MERGE_TOOL_PRESETS,
    SHORT_DATE_PRESETS,
    prefs,
    qtIsNativeMacosStyle,
)
from gitfourchette.toolbox import *
from gitfourchette.trtables import TrTables

logger = logging.getLogger(__name__)

SAMPLE_SIGNATURE = Signature("Jean-Michel Tartempion", "jm.tarte@example.com", 0, 0)
SAMPLE_FILE_PATH = "spam/.ham/eggs/hello.c"


def _boxWidget(layout, *controls):
    layout.setSpacing(0)
    layout.setContentsMargins(0, 0, 0, 0)
    for control in controls:
        if control == "stretch":
            layout.addStretch()
        else:
            layout.addWidget(control)
    w = QWidget()
    w.setLayout(layout)
    return w


def vBoxWidget(*controls):
    return _boxWidget(QVBoxLayout(), *controls)


def hBoxWidget(*controls):
    return _boxWidget(QHBoxLayout(), *controls)


def splitSettingKey(n):
    split = n.split('_', 1)
    if len(split) == 1:
        category = "general"
        item = split[0]
    else:
        category, item = split
    return category, item


class PrefsDialog(QDialog):
    lastOpenTab = 0

    @staticmethod
    def saveLastOpenTab(i):
        PrefsDialog.lastOpenTab = i

    def __init__(self, parent: QWidget, focusOn: str = ""):
        super().__init__(parent)

        # Hide irrelevant settings
        skipKeys = {"shortHashChars", "toolBarButtonStyle", "toolBarIconSize"}
        if MACOS:
            skipKeys.add("autoHideMenuBar")
        if not FREEDESKTOP:
            skipKeys.add("debug_forceQtApi")
        if not QSoundEffect:
            skipKeys.add("debug_taskClicks")

        self.setObjectName("PrefsDialog")

        self.setWindowTitle(translate("Prefs", "{app} Preferences", "prefs dialog title").format(app=qAppName()))

        buttonBox = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)


        # Delta to on-disk preferences.
        self.prefDiff = {}

        tabWidget = QTabWidget(self)

        # Make tabs vertical if possible (macOS style: too messy)
        if qtIsNativeMacosStyle():
            tabWidget.setTabPosition(QTabWidget.TabPosition.North)
        else:
            # Pass a string to the proxy's ctor, NOT QApplication.style() as this would transfer the ownership
            # of the style to the proxy!!!
            proxyStyle = QTabBarStyleNoRotatedText(prefs.qtStyle)
            tabWidget.setStyle(proxyStyle)
            tabWidget.setTabPosition(QTabWidget.TabPosition.West if self.isLeftToRight() else QTabWidget.TabPosition.East)

        pCategory = "~~~dummy~~~"
        form: QFormLayout = None

        categoryForms = {}

        for prefKey in prefs.__dict__:
            if prefKey in skipKeys or prefKey.startswith("_"):
                continue

            prefValue = prefs.__dict__[prefKey]
            category, caption = splitSettingKey(prefKey)
            prefType = type(prefValue)

            if category != pCategory:
                formContainer = QWidget(self)
                form = QFormLayout(formContainer)
                form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
                formContainer.setLayout(form)
                tabName = TrTables.prefKey(category) if category else translate("Prefs", "General")
                tabWidget.addTab(formContainer, tabName)
                categoryForms[category] = form
                pCategory = category

                headerText = TrTables.prefKey(f"{category}_HEADER")
                if headerText != f"{category}_HEADER":
                    headerText = headerText.format(app=qAppName())
                    explainer = QLabel(headerText)
                    explainer.setWordWrap(True)
                    explainer.setTextFormat(Qt.TextFormat.RichText)
                    form.addRow(explainer)

            suffix = ""
            if caption:
                caption = TrTables.prefKey(prefKey)
                if "#" in caption:
                    caption, suffix = caption.split("#")
                    caption = caption.rstrip()
                    suffix = suffix.lstrip()

            if prefKey == 'language':
                control = self.languageControl(prefKey, prefValue)
            elif prefKey == 'qtStyle':
                control = self.qtStyleControl(prefKey, prefValue)
            elif prefKey == 'diff_font':
                control = self.fontControl(prefKey)
            elif prefKey == 'shortTimeFormat':
                control = self.dateFormatControl(prefKey, prefValue, SHORT_DATE_PRESETS)
            elif prefKey == 'pathDisplayStyle':
                control = self.enumControl(prefKey, prefValue, prefType, previewCallback=lambda v: abbreviatePath(SAMPLE_FILE_PATH, v))
            elif prefKey == 'authorDisplayStyle':
                control = self.enumControl(prefKey, prefValue, prefType, previewCallback=lambda v: abbreviatePerson(SAMPLE_SIGNATURE, v))
            elif prefKey == 'shortHashChars':
                control = self.boundedIntControl(prefKey, prefValue, 4, 40)
            elif prefKey == 'maxRecentRepos':
                control = self.boundedIntControl(prefKey, prefValue, 0, 50)
            elif prefKey == 'diff_contextLines':  # staging/discarding individual lines is flaky with 0 context lines
                control = self.boundedIntControl(prefKey, prefValue, 1, 32)
            elif prefKey == 'diff_tabSpaces':
                control = self.boundedIntControl(prefKey, prefValue, 1, 16)
            elif prefKey == 'external_editor':
                control = self.strControlWithPresets(prefKey, prefValue, EDITOR_TOOL_PRESETS, leaveBlankHint=True)
            elif prefKey == 'external_diff':
                control = self.strControlWithPresets(prefKey, prefValue, DIFF_TOOL_PRESETS)
            elif prefKey == 'external_merge':
                control = self.strControlWithPresets(prefKey, prefValue, MERGE_TOOL_PRESETS)
            elif issubclass(prefType, enum.Enum):
                control = self.enumControl(prefKey, prefValue, prefType)
            elif prefType is str:
                control = self.strControl(prefKey, prefValue)
            elif prefType is int:
                control = self.intControl(prefKey, prefValue)
            elif prefType is float:
                control = self.floatControl(prefKey, prefValue)
            elif prefType is bool:
                trueText = TrTables.prefKeyNoDefault(prefKey + "_true")
                falseText = TrTables.prefKeyNoDefault(prefKey + "_false")
                if trueText or falseText:
                    control = self.boolComboBoxControl(prefKey, prefValue, trueName=trueText, falseName=falseText)
                else:
                    control = QCheckBox(caption, self)
                    control.setCheckState(Qt.CheckState.Checked if prefValue else Qt.CheckState.Unchecked)
                    control.stateChanged.connect(lambda v, k=prefKey, c=control: self.assign(k, c.isChecked()))  # PySide6: "v==Qt.CheckState.Checked" doesn't work anymore?
                    caption = None  # The checkbox contains its own caption

            toolTip = TrTables.prefKeyNoDefault(prefKey + "_help")

            extraWidgets = []

            if suffix:
                extraWidgets.append(QLabel(suffix))

            if toolTip:
                toolTip = toolTip.format(app=qAppName())
                control.setToolTip(toolTip)

                hintButton = QToolButton(self)
                hintButton.setIcon(stockIcon("hint"))
                hintButton.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                hintButton.setAutoRaise(True)
                hintButton.setToolTip(toolTip)
                hintButton.clicked[bool].connect(lambda _, w=hintButton, t=toolTip: QToolTip.showText(QCursor.pos(), t, w))  # [bool]: for PySide <6.7.0 (PYSIDE-2524)
                extraWidgets.append(hintButton)

            if extraWidgets:
                hbl = QHBoxLayout()
                hbl.addWidget(control)
                for w in extraWidgets:
                    hbl.addWidget(w)
                if control.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Minimum:
                    # Stick help button to the right edge of non-expanding widget
                    hbl.addStretch()
                addToForm = hbl
            else:
                addToForm = control

            if caption:
                caption += self.tr(":", "caption suffix in prefs dialog")
                captionLabel = QLabel(caption)
                captionLabel.setBuddy(control)
                if toolTip:
                    captionLabel.setToolTip(toolTip)
                    # captionLabel.setCursor(Qt.CursorShape.WhatsThisCursor)
                form.addRow(captionLabel, addToForm)
            else:
                form.addRow(addToForm)

            if focusOn == prefKey:
                tabWidget.setCurrentWidget(formContainer)
                control.setFocus()

        layout = QVBoxLayout()
        layout.addWidget(tabWidget)
        layout.addWidget(buttonBox)
        self.setLayout(layout)

        if not focusOn:
            # Restore last open tab
            tabWidget.setCurrentIndex(PrefsDialog.lastOpenTab)
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

    def languageControl(self, prefKey: str, prefValue: str):
        defaultCaption = translate("Prefs", "System default", "system default language setting")
        control = QComboBox(self)
        control.addItem(defaultCaption, userData="")
        if not prefValue:
            control.setCurrentIndex(0)
        control.insertSeparator(1)
        for enumMember in LANGUAGES:
            lang = QLocale(enumMember)
            control.addItem(lang.nativeLanguageName(), enumMember)
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

        def pickFont():
            result = QFontDialog.getFont(currentFont(), parent=self)
            if PYQT5 or PYQT6:
                newFont, ok = result
            else:
                ok, newFont = result
            if ok:
                self.assign(prefKey, newFont.toString())
                refreshFontButton()

        fontButton = QPushButton(translate("Prefs", "Font"))
        fontButton.clicked.connect(lambda e: pickFont())
        fontButton.setMinimumWidth(256)
        fontButton.setMaximumWidth(256)
        fontButton.setMaximumHeight(128)

        resetButton = QToolButton(self)
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

    def strControl(self, prefKey, prefValue):
        control = QLineEdit(prefValue, self)
        control.textEdited.connect(lambda v, k=prefKey: self.assign(k, v))
        return control

    def strControlWithPresets(self, prefKey, prefValue, presets, leaveBlankHint=False):
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
        return control

    def intControl(self, prefKey, prefValue):
        control = QLineEdit(str(prefValue), self)
        control.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        control.setValidator(QIntValidator())
        control.textEdited.connect(lambda v, k=prefKey: self.assign(k, int(v) if v else 0))
        return control

    def boundedIntControl(self, prefKey, prefValue, minValue, maxValue):
        control = QSpinBox(self)
        control.setMinimum(minValue)
        control.setMaximum(maxValue)
        control.setValue(prefValue)
        control.valueChanged.connect(lambda v, k=prefKey: self.assign(k, v))
        return control

    def floatControl(self, prefKey, prefValue):
        control = QLineEdit(str(prefValue), self)
        control.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        control.setValidator(QDoubleValidator())
        control.textEdited.connect(lambda v, k=prefKey: self.assign(k, float(v) if v else 0.0))
        return control

    def boolRadioControl(self, prefKey, prefValue, falseName, trueName):
        falseButton = QRadioButton(falseName)
        falseButton.setChecked(not prefValue)
        falseButton.toggled.connect(lambda b: self.assign(prefKey, not b))

        trueButton = QRadioButton(trueName)
        trueButton.setChecked(prefValue)
        trueButton.toggled.connect(lambda b: self.assign(prefKey, b))

        return vBoxWidget(trueButton, falseButton)

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
