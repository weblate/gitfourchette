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


def prettifyCamelCase(x):
    x = re.sub(r'([A-Z]+)', r' \1', x)
    return x[0].upper() + x[1:]


def prettifySnakeCase(x):
    return x.replace('_', ' ').title()


def prettifySetting(n):
    split = n.split('_', 1)
    if len(split) == 1:
        category = None
        item = split[0]
    else:
        category, item = split
    if category:
        category = prettifyCamelCase(category)
    item = prettifyCamelCase(item)
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

        self.setObjectName("PrefsDialog")

        self.setWindowTitle(F"{QApplication.applicationDisplayName()} Preferences")

        buttonBox = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)


        # Delta to on-disk preferences.
        self.prefDiff = {}

        tabWidget = QTabWidget(self)
        tabWidget.setTabPosition(QTabWidget.TabPosition.North)

        pCategory = "~~~dummy~~~"
        form: QFormLayout = None

        for prefKey in prefs.__dict__:
            prefValue = prefs.__dict__[prefKey]
            category, caption = prettifySetting(prefKey)
            prefType = type(prefValue)

            if category != pCategory:
                formContainer = QWidget(self)
                form = QFormLayout(formContainer)
                form.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)
                formContainer.setLayout(form)
                tabWidget.addTab(formContainer, category or "General")
                pCategory = category

            if prefKey == 'language':
                control = self.languageControl(prefKey, prefValue)
            elif prefKey == 'qtStyle':
                control = self.qtStyleControl(prefKey, prefValue)
            elif prefKey == 'diff_font':
                control = self.fontControl(prefKey)
            elif prefKey == 'graph_chronologicalOrder':
                caption = "Commit Order"
                control = self.boolRadioControl(prefKey, prefValue, trueName="Chronological", falseName="Topological")
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
                control.stateChanged.connect(lambda v, k=prefKey: self.assign(k, v != Qt.CheckState.Unchecked))
                caption = None  # The checkbox contains its own caption

            if caption:
                form.addRow(caption, control)
            else:
                form.addRow(control)

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
            if qtBindingName == "pyqt5":
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
                fontButton.setText(F"Default ({font.family()} {font.pointSize()})")
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
            control.addItem(prettifySnakeCase(enumMember.name), enumMember)
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
