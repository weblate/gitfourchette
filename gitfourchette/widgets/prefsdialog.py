from gitfourchette import log
from gitfourchette.qt import *
from gitfourchette.settings import prefs, SHORT_DATE_PRESETS, LANGUAGES
from gitfourchette.util import abbreviatePath
from gitfourchette.widgets.graphdelegate import abbreviatePerson
import datetime
import enum
import re
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


class ComboBoxWithPreview(QComboBox):
    class ItemDelegate(QStyledItemDelegate):
        def __init__(self, parent, previewCallback):
            super().__init__(parent)
            self.previewCallback = previewCallback

        def paint(self, painter, option, index):
            super().paint(painter, option, index)

            painter.save()

            pw: QWidget = self.parent()

            rect = QRect(option.rect)
            rect.setLeft(rect.left() + pw.width())

            painter.setPen(option.palette.color(QPalette.ColorGroup.Normal, QPalette.ColorRole.PlaceholderText))
            painter.drawText(rect, Qt.AlignmentFlag.AlignVCenter, self.previewCallback(index.data(Qt.ItemDataRole.UserRole)))
            painter.restore()

    def __init__(self, parent, previewCallback):
        super().__init__(parent)
        delegate = ComboBoxWithPreview.ItemDelegate(self, previewCallback)
        self.setItemDelegate(delegate)

    def showPopup(self):
        self.view().setMinimumWidth(300)
        super().showPopup()


class DatePresetDelegate(QStyledItemDelegate):
    def __init__(self, parent):
        super().__init__(parent)

    def paint(self, painter, option, index):
        super().paint(painter, option, index)

        painter.save()
        name, format, now = index.data(Qt.ItemDataRole.UserRole)
        if option.state & QStyle.StateFlag.State_Selected:
            painter.setPen(option.palette.color(QPalette.ColorGroup.Normal, QPalette.ColorRole.HighlightedText))
        painter.drawText(option.rect, Qt.AlignmentFlag.AlignVCenter, F"{name}")
        painter.setPen(option.palette.color(QPalette.ColorGroup.Normal, QPalette.ColorRole.PlaceholderText))

        rect = QRect(option.rect)
        rect.setLeft(rect.left() + painter.fontMetrics().horizontalAdvance("M"*8))

        painter.drawText(rect, Qt.AlignmentFlag.AlignVCenter, F"{now.strftime(format)}")
        painter.restore()


class PrefsDialog(QDialog):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.settingsTranslationTable = {}
        self.initSettingsTranslationTable()

        self.setObjectName("PrefsDialog")

        self.setWindowTitle(self.tr("{0} Preferences", "{0} = GitFourchette").format(QApplication.applicationDisplayName()))

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
                form.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)
                formContainer.setLayout(form)
                tabWidget.addTab(formContainer, self.translateSetting(category) or self.tr("General"))
                categoryForms[category] = form
                pCategory = category

            if caption:
                caption = self.translateSetting(prefKey)
                if isinstance(caption, tuple):
                    caption, suffix = caption
                else:
                    suffix = ""

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

        explainer = QLabel(
            self.tr("When you discard changes from the working directory, "
                    "{0} keeps a temporary copy in a hidden “trash” folder. "
                    "This gives you a last resort to rescue changes that you have discarded by mistake. "
                    "You can look around this trash folder via <i>“Repo &rarr; Rescue Discarded Changes”</i>."
                    ).format(QApplication.instance().applicationName()))
        explainer.setTextFormat(Qt.TextFormat.RichText)
        explainer.setWordWrap(True)
        categoryForms["trash"].insertRow(0, explainer)

        layout = QVBoxLayout()
        layout.addWidget(tabWidget)
        layout.addWidget(buttonBox)
        self.setLayout(layout)

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
            control = ComboBoxWithPreview(self, previewCallback)
        else:
            control = QComboBox(self)

        for enumMember in enumType:
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
        now = datetime.datetime(1999, 12, 31, 23, 59)
        bogusTime = "Wednesday, December 99, 9999 99:99:99 AM"

        def onEditTextChanged(text):
            preview.setText(now.strftime(text))
            self.assign(prefKey, text)

        def onCurrentIndexChanged(i):
            if i < 0 or i >= len(presets):
                return
            control.setCurrentIndex(-1)
            control.setEditText(presets[i][1])

        preview = QLabel(bogusTime)
        preview.setEnabled(False)
        preview.setMaximumWidth(preview.fontMetrics().horizontalAdvance(bogusTime))

        control = QComboBox()
        control.setEditable(True)
        for preset in presets:
            control.addItem("", (*preset, now))
        control.currentIndexChanged.connect(onCurrentIndexChanged)
        control.editTextChanged.connect(onEditTextChanged)
        control.setItemDelegate(DatePresetDelegate(parent=control))
        control.setMinimumWidth(200)
        control.setCurrentIndex(-1)
        control.view().setMinimumWidth(control.fontMetrics().horizontalAdvance(bogusTime))

        control.setEditText(prefValue)

        return vBoxWidget(control, preview)

    def translateSetting(self, s: str):
        return self.settingsTranslationTable.get(s, s)

    def initSettingsTranslationTable(self):
        self.settingsTranslationTable = {
            "general": self.tr("General"),
            "diff": self.tr("Diff"),
            "tabs": self.tr("Tabs"),
            "graph": self.tr("Graph"),
            "trash": self.tr("Trash"),
            "debug": self.tr("Debug"),

            "language": self.tr("Language"),
            "qtStyle": self.tr("Theme"),
            "fileWatcher": self.tr("File watcher"),
            "shortHashChars": (self.tr("Shorten hashes to"), self.tr("characters")),
            "shortTimeFormat": self.tr("Short time format"),
            "pathDisplayStyle": self.tr("Path display style"),
            "authorDisplayStyle": self.tr("Author display style"),
            "maxRecentRepos": self.tr("Max recent repos"),
            "showStatusBar": self.tr("Show status bar"),
            "autoHideMenuBar": self.tr("Toggle menu bar visibility with Alt key"),

            "diff_font": self.tr("Font"),
            "diff_tabSpaces": (self.tr("One tab is"), self.tr("spaces")),
            "diff_largeFileThresholdKB": (self.tr("Max diff size"), self.tr("KB")),
            "diff_imageFileThresholdKB": (self.tr("Max image size"), self.tr("KB")),
            "diff_wordWrap": self.tr("Word wrap"),
            "diff_showStrayCRs": self.tr("Highlight stray “CR” characters"),
            "diff_colorblindFriendlyColors": self.tr("Colorblind-friendly color scheme"),

            "tabs_closeButton": self.tr("Show tab close button"),
            "tabs_expanding": self.tr("Tab bar takes all available width"),
            "tabs_autoHide": self.tr("Auto-hide tab bar if there’s just 1 tab"),
            "tabs_doubleClickOpensFolder": self.tr("Double-click a tab to open repo folder"),

            "graph_chronologicalOrder": self.tr("Commit order"),
            "graph_flattenLanes": self.tr("Flatten lanes"),

            "trash_maxFiles": (self.tr("Max discarded patches in the trash"), self.tr("files")),
            "trash_maxFileSizeKB": (self.tr("Don’t salvage patches bigger than"), self.tr("KB")),

            "debug_showMemoryIndicator": self.tr("Show memory indicator in status bar"),
            "debug_showPID": self.tr("Show technical info in title bar"),
            "debug_verbosity": self.tr("Logging verbosity"),

            "FULL_PATHS": self.tr("Full paths"),
            "ABBREVIATE_DIRECTORIES": self.tr("Abbreviate directories"),
            "SHOW_FILENAME_ONLY": self.tr("Show filename only"),

            "FULL_NAME": self.tr("Full name"),
            "FIRST_NAME": self.tr("First name"),
            "LAST_NAME": self.tr("Last name"),
            "INITIALS": self.tr("Initials"),
            "FULL_EMAIL": self.tr("Full email"),
            "ABBREVIATED_EMAIL": self.tr("Abbreviated email"),
        }

