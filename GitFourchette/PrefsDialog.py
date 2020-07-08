from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *
import datetime
import re
from settings import prefs, monoFont, PROGRAM_NAME, SHORT_DATE_PRESETS, LONG_DATE_PRESETS


def prettifyCamelCase(x):
    x = re.sub(r'([A-Z]+)', r' \1', x)
    return x[0].upper() + x[1:]


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

        self.setWindowTitle(F"{PROGRAM_NAME} Preferences")

        buttonBox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)

        layout = QVBoxLayout()

        # Delta to on-disk preferences.
        self.prefDiff = {}

        tabWidget = QTabWidget(self)
        tabWidget.setTabPosition(QTabWidget.TabPosition.North)
        layout.addWidget(tabWidget)

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
                control = self.namedBoolControl(prefKey, prefValue, "Chronological", "Topological")
            elif prefKey == 'shortTimeFormat':
                control = self.dateFormatControl(prefKey, prefValue, SHORT_DATE_PRESETS)
            elif prefKey == 'longTimeFormat':
                continue  # Don't expose the setting for this
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

        layout.addWidget(buttonBox)
        self.setLayout(layout)

    def assign(self, k, v):
        if prefs.__dict__[k] == v:
            print("Reverting to original value:", k, v, prefs.__dict__[k])
            if k in self.prefDiff:
                del self.prefDiff[k]
        else:
            print(k, prefs.__dict__[k], v)
            self.prefDiff[k] = v

    def fontControl(self, prefKey, prefValue):
        control = QFontComboBox()
        control.setCurrentFont(monoFont)  # TODO : use prefValue
        control.currentFontChanged.connect(lambda v, k=prefKey: self.assign(k, v.toString()))
        return control

    def strControl(self, prefKey, prefValue):
        control = QLineEdit(prefValue, self)
        control.textEdited.connect(lambda v, k=prefKey: self.assign(k, v))
        return control

    def intControl(self, prefKey, prefValue):
        control = QLineEdit(str(prefValue), self)
        control.setValidator(QIntValidator())
        control.textEdited.connect(lambda v, k=prefKey: self.assign(k, int(v) if v else 0))
        return control

    def floatControl(self, prefKey, prefValue):
        control = QLineEdit(str(prefValue), self)
        control.setValidator(QDoubleValidator())
        control.textEdited.connect(lambda v, k=prefKey: self.assign(k, float(v) if v else 0.0))
        return control

    def namedBoolControl(self, prefKey, prefValue, falseName, trueName):
        control = QComboBox()
        control.addItem(falseName)
        control.addItem(trueName)
        control.setCurrentIndex(1 if prefValue else 0)
        control.currentIndexChanged.connect(lambda v, k=prefKey: self.assign(k, v == 1))
        return control

    def qtStyleControl(self, prefKey, prefValue):
        control = QComboBox()

        control.addItem("System default")
        if not prefValue:
            control.setCurrentIndex(0)
        control.insertSeparator(1)
        for i, availableStyle in enumerate(QStyleFactory.keys()):
            control.addItem(availableStyle)
            if prefValue == availableStyle:
                control.setCurrentIndex(i)
        control.textActivated.connect(lambda v, k=prefKey: self.assign(k, v))
        return control

    def dateFormatControl(self, prefKey, prefValue, presets):
        now = datetime.datetime.now(datetime.timezone.utc).astimezone()
        bogusTime = "Wednesday, December 99, 9999 99:99:99 AM"

        def onEditTextChanged(text):
            preview.setText(now.strftime(text))
            self.assign(prefKey, text)

        def onCurrentIndexChanged(i):
            if i < 0: return
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

        group = QWidget()
        group.setLayout(QVBoxLayout())
        group.layout().setMargin(0)
        group.layout().setSpacing(0)
        group.layout().addWidget(control)
        group.layout().addWidget(preview)
        return group