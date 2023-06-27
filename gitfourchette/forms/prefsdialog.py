from gitfourchette import log
from gitfourchette import trtables
from gitfourchette.qt import *
from gitfourchette.settings import prefs, SHORT_DATE_PRESETS, LANGUAGES, DIFF_TOOL_PRESETS, MERGE_TOOL_PRESETS
from gitfourchette.toolbox import *
from gitfourchette.graphview.commitlogdelegate import abbreviatePerson
import enum
import pygit2


SAMPLE_SIGNATURE = pygit2.Signature("Jean-Michel Tartempion", "jm.tarte@example.com", 0, 0)
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

        self.settingsTranslationTable = trtables.prefsTranslationTable()

        self.setObjectName("PrefsDialog")

        self.setWindowTitle(self.tr("{app} Preferences").format(app=qAppName()))

        buttonBox = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)


        # Delta to on-disk preferences.
        self.prefDiff = {}

        tabWidget = QTabWidget(self)
        tabWidget.setTabPosition(QTabWidget.TabPosition.North)

        pCategory = "~~~dummy~~~"
        form: QFormLayout = None

        categoryForms = {}

        for prefKey in prefs.__dict__:
            prefValue = prefs.__dict__[prefKey]
            category, caption = splitSettingKey(prefKey)
            prefType = type(prefValue)

            if category != pCategory:
                formContainer = QWidget(self)
                form = QFormLayout(formContainer)
                form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
                formContainer.setLayout(form)
                tabWidget.addTab(formContainer, self.translateSetting(category) or self.tr("General"))
                categoryForms[category] = form
                pCategory = category

                headerText = self.translateSetting(f"{category}_HEADER")
                if headerText != f"{category}_HEADER":
                    headerText = headerText.format(app=qAppName())
                    explainer = QLabel(headerText)
                    explainer.setWordWrap(True)
                    explainer.setTextFormat(Qt.TextFormat.RichText)
                    form.addRow(explainer)

            suffix = ""
            if caption:
                caption = self.translateSetting(prefKey)
                if isinstance(caption, tuple):
                    caption, suffix = caption

            if prefKey == 'language':
                control = self.languageControl(prefKey, prefValue)
            elif prefKey == 'qtStyle':
                control = self.qtStyleControl(prefKey, prefValue)
            elif prefKey == 'diff_font':
                control = self.fontControl(prefKey)
            elif prefKey == 'graph_chronologicalOrder':
                control = self.boolRadioControl(prefKey, prefValue, trueName=self.tr("Chronological"), falseName=self.tr("Topological"))
            elif prefKey == 'shortTimeFormat':
                control = self.dateFormatControl(prefKey, prefValue, SHORT_DATE_PRESETS)
            elif prefKey == 'pathDisplayStyle':
                control = self.enumControl(prefKey, prefValue, prefType, previewCallback=lambda v: abbreviatePath(SAMPLE_FILE_PATH, v))
            elif prefKey == 'authorDisplayStyle':
                control = self.enumControl(prefKey, prefValue, prefType, previewCallback=lambda v: abbreviatePerson(SAMPLE_SIGNATURE, v))
            elif prefKey == 'shortHashChars':
                control = self.boundedIntControl(prefKey, prefValue, 0, 40)
            elif prefKey == 'maxRecentRepos':
                control = self.boundedIntControl(prefKey, prefValue, 0, 50)
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
                control = QCheckBox(caption, self)
                control.setCheckState(Qt.CheckState.Checked if prefValue else Qt.CheckState.Unchecked)
                control.stateChanged.connect(lambda v, k=prefKey, c=control: self.assign(k, c.isChecked()))  # PySide6: "v==Qt.CheckState.Checked" doesn't work anymore?
                caption = None  # The checkbox contains its own caption

            if suffix:
                hbl = QHBoxLayout()
                hbl.addWidget(control)
                hbl.addWidget(QLabel(suffix))
                control = hbl

            if caption:
                form.addRow(caption, control)
            else:
                form.addRow(control)

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

        tabWidget.currentChanged.connect(PrefsDialog.saveLastOpenTab)

        self.setModal(True)

    def assign(self, k, v):
        if prefs.__dict__[k] == v:
            if k in self.prefDiff:
                del self.prefDiff[k]
        else:
            self.prefDiff[k] = v
        log.info("prefsdialog", f"Assign {k} {v}")

    def getMostRecentValue(self, k):
        if k in self.prefDiff:
            return self.prefDiff[k]
        elif k in prefs.__dict__:
            return prefs.__dict__[k]
        else:
            return None

    def languageControl(self, prefKey: str, prefValue: str):
        control = QComboBox(self)

        control.addItem(self.tr("System default"), userData="")
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

        fontButton = QPushButton(self.tr("Font"))
        fontButton.clicked.connect(lambda e: pickFont())
        fontButton.setMinimumWidth(256)
        fontButton.setMaximumWidth(256)
        fontButton.setMaximumHeight(128)

        resetButton = QToolButton(self)
        resetButton.setText(self.tr("Reset"))
        resetButton.clicked.connect(lambda: resetFont())

        def refreshFontButton():
            font = currentFont()
            if not self.getMostRecentValue(prefKey):
                resetButton.setVisible(False)
                fontButton.setText(self.tr("Default", "as in Default Font") + f" ({font.family()} {font.pointSize()})")
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

    def strControlWithPresets(self, prefKey, prefValue, presets):
        control = QComboBoxWithPreview(self)
        control.setEditable(True)

        for k in presets:
            control.addItemWithPreview(k, presets[k], presets[k])
            if prefValue == presets[k]:
                control.setCurrentIndex(control.count()-1)

        control.setEditText(prefValue)
        control.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred))

        control.editTextChanged.connect(lambda text: self.assign(prefKey, text))
        return control

    def intControl(self, prefKey, prefValue):
        control = QLineEdit(str(prefValue), self)
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

    def enumControl(self, prefKey, prefValue, enumType, previewCallback=None):
        if previewCallback:
            control = QComboBoxWithPreview(self)
        else:
            control = QComboBox(self)

        for enumMember in enumType:
            if previewCallback:
                control.addItemWithPreview(self.translateSetting(enumMember.name), enumMember, previewCallback(enumMember))
            else:
                control.addItem(self.translateSetting(enumMember.name), enumMember)
            if prefValue == enumMember:
                control.setCurrentIndex(control.count() - 1)

        control.activated.connect(lambda index: self.assign(prefKey, control.currentData(Qt.ItemDataRole.UserRole)))
        return control

    def qtStyleControl(self, prefKey, prefValue):
        control = QComboBox(self)

        control.addItem(self.tr("System default"), userData="")
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

    def translateSetting(self, s: str):
        return self.settingsTranslationTable.get(s, s)
