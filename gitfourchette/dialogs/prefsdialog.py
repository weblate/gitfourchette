from allqt import *
from settings import prefs, SHORT_DATE_PRESETS
import datetime
import enum
import re


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


class DatePresetDelegate(QStyledItemDelegate):
    def __init__(self, parent):
        super().__init__(parent)

    def paint(self, painter, option, index):
        super().paint(painter, option, index)

        painter.save()
        name, format, now = index.data(Qt.UserRole)
        if option.state & QStyle.State_Selected:
            painter.setPen(option.palette.color(QPalette.ColorGroup.Normal, QPalette.ColorRole.HighlightedText))
        painter.drawText(option.rect, Qt.AlignVCenter, F"{name}")
        painter.setPen(option.palette.color(QPalette.ColorGroup.Normal, QPalette.ColorRole.PlaceholderText))


        rekt = QRect(option.rect)
        rekt.setLeft(rekt.left() + painter.fontMetrics().horizontalAdvance("M"*8))

        painter.drawText(rekt, Qt.AlignVCenter, F"{now.strftime(format)}")
        painter.restore()


class PrefsDialog(QDialog):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.setWindowTitle(F"{QApplication.applicationDisplayName()} Preferences")

        buttonBox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
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
            t = type(prefValue)

            if category != pCategory:
                formContainer = QWidget(self)
                form = QFormLayout(formContainer)
                form.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)
                formContainer.setLayout(form)
                tabWidget.addTab(formContainer, category or "General")
                pCategory = category

            if prefKey == 'qtStyle':
                control = self.qtStyleControl(prefKey, prefValue)
            elif prefKey == 'diff_font':
                control = self.fontControl(prefKey, prefValue)
            elif prefKey == 'graph_topoOrder':
                caption = "Commit Order"
                control = self.boolRadioControl(prefKey, prefValue, falseName="Chronological", trueName="Topological")
            elif prefKey == 'shortTimeFormat':
                control = self.dateFormatControl(prefKey, prefValue, SHORT_DATE_PRESETS)
            elif prefKey == 'shortHashChars':
                control = self.boundedIntControl(prefKey, prefValue, 0, 40)
            elif issubclass(t, enum.Enum):
                control = self.enumControl(prefKey, prefValue, t)
            elif t is str:
                control = self.strControl(prefKey, prefValue)
            elif t is int:
                control = self.intControl(prefKey, prefValue)
            elif t is float:
                control = self.floatControl(prefKey, prefValue)
            elif t is bool:
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
            print("Reverting to original value:", k, v, prefs.__dict__[k])
            if k in self.prefDiff:
                del self.prefDiff[k]
        else:
            print(k, prefs.__dict__[k], v)
            self.prefDiff[k] = v

    def fontControl(self, prefKey, prefValue):
        def onSizeChanged(strValue):
            points = int(strValue) if strValue else 11
            font = control.currentFont()
            font.setPointSize(points)
            self.assign(prefKey, font.toString())
            control.setCurrentFont(font)

        font = QFont()
        font.fromString(prefValue)

        control = QFontComboBox()
        control.setCurrentFont(font)  # TODO : use prefValue
        control.currentFontChanged.connect(lambda v, k=prefKey: [
            self.assign(k, v.toString()) ])

        sizeControl = QLineEdit(str(font.pointSize()), self)
        sizeControl.setValidator(QIntValidator())
        sizeControl.textEdited.connect(onSizeChanged)
        sizeControl.setMaximumWidth(sizeControl.fontMetrics().horizontalAdvance("000000"))

        # TODO: after unchecking the filter checkbox, the QFontComboBox isn't fully repopulated because its item count seems to be fixed
        '''
        fixedWidthFilter = QCheckBox("Show fixed-width only")
        fixedWidthFilter.stateChanged.connect(lambda v:
                control.setFontFilters(QFontComboBox.AllFonts if v == Qt.CheckState.Unchecked else QFontComboBox.MonospacedFonts))
        if QFontDatabase().isFixedPitch(font.family()):
            fixedWidthFilter.setCheckState(Qt.CheckState.Checked)
        else:
            fixedWidthFilter.setCheckState(Qt.CheckState.Unchecked)
        '''

        return vBoxWidget(
            control,
            #fixedWidthFilter,
            hBoxWidget(
                QLabel("Size:  "),
                sizeControl,
                "stretch"
            )
        )

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
        label = QLabel(str(prefValue), self)
        label.setMinimumWidth(label.fontMetrics().horizontalAdvance("000"))

        control = QSlider(Qt.Horizontal, self)
        control.setMinimumWidth(40*3)
        control.setMinimum(minValue)
        control.setMaximum(maxValue)
        control.setValue(prefValue)
        control.valueChanged.connect(lambda v, k=prefKey: self.assign(k, v))
        control.valueChanged.connect(lambda v: label.setText(str(v)))
        return hBoxWidget(label, control)

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

    def enumControl(self, prefKey, prefValue, enumType):
        control = QComboBox(self)
        for enumMember in enumType:
            control.addItem(prettifySnakeCase(enumMember.name), enumMember)
            if prefValue == enumMember:
                control.setCurrentIndex(control.count() - 1)
        control.activated.connect(lambda index: self.assign(prefKey, control.currentData(Qt.UserRole)))
        return control

    def qtStyleControl(self, prefKey, prefValue):
        control = QComboBox(self)

        control.addItem("System default")
        if not prefValue:
            control.setCurrentIndex(0)
        control.insertSeparator(1)
        for availableStyle in QStyleFactory.keys():
            control.addItem(availableStyle)
            if prefValue == availableStyle:
                control.setCurrentIndex(control.count() - 1)
        control.textActivated.connect(lambda v, k=prefKey: self.assign(k, v))
        return control

    def dateFormatControl(self, prefKey, prefValue, presets):
        now = datetime.datetime.now(datetime.timezone.utc).astimezone()
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
