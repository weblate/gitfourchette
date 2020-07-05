from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *

import re
from settings import prefs, monoFont, PROGRAM_NAME


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


class PrefsDialog(QDialog):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.setWindowTitle(F"{PROGRAM_NAME} Preferences")
        #self.setMinimumSize(QSize(512, 384))

        self.buttonBox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)

        self.layout = QVBoxLayout()

        # Delta to on-disk preferences.
        self.prefDiff = {}

        qtw = QTabWidget(self)
        qtw.setTabPosition(QTabWidget.TabPosition.North)
        self.layout.addWidget(qtw)

        pCategory = "~~~dummy~~~"
        form: QFormLayout = None

        for k in prefs.__dict__:
            value = prefs.__dict__[k]
            category, caption = prettifySetting(k)
            t = type(value)

            if category != pCategory:
                w = QWidget(self)
                form = QFormLayout(w)
                form.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)
                w.setLayout(form)
                qtw.addTab(w, category or "General")
                pCategory = category

            if k == 'qtStyle':
                qcb = QComboBox()
                i = 0
                for availableStyle in QStyleFactory.keys():
                    qcb.addItem(availableStyle)
                    if prefs.qtStyle == availableStyle:
                        qcb.setCurrentIndex(i)
                    i += 1
                qcb.textActivated.connect(lambda v, k=k: self.assign(k, v))
                form.addRow(caption, qcb)
            elif k == 'diff_font':
                qfcb = QFontComboBox()
                qfcb.setCurrentFont(monoFont)
                qfcb.currentFontChanged.connect(lambda v, k=k: self.assign(k, v.toString()))
                form.addRow(caption, qfcb)
            elif k == 'graph_topoOrder':
                qcb = QComboBox()
                qcb.addItem("Chronological")
                qcb.addItem("Topological")
                qcb.setCurrentIndex(1 if value else 0)
                qcb.currentIndexChanged.connect(lambda v, k=k: self.assign(k, v == 1))
                form.addRow("Commit Order", qcb)
            elif t is str:
                qle = QLineEdit(value, self)
                form.addRow(caption, qle)
                qle.textEdited.connect(lambda v, k=k: self.assign(k, v))
            elif t is int:
                qle = QLineEdit(str(value), self)
                qle.setValidator(QIntValidator())
                form.addRow(caption, qle)
                qle.textEdited.connect(lambda v, k=k: self.assign(k, int(v) if v else 0))
            elif t is float:
                qle = QLineEdit(str(value), self)
                qle.setValidator(QDoubleValidator())
                form.addRow(caption, qle)
                qle.textEdited.connect(lambda v, k=k: self.assign(k, float(v) if v else 0.0))
            elif t is bool:
                qcb = QCheckBox(caption, self)
                qcb.setCheckState(Qt.CheckState.Checked if value else Qt.CheckState.Unchecked)
                form.addRow(qcb)
                qcb.stateChanged.connect(lambda v, k=k: self.assign(k, v != Qt.CheckState.Unchecked))
            else:
                form.addWidget(QLabel("???"+caption))

        self.layout.addWidget(self.buttonBox)
        self.setLayout(self.layout)

    def assign(self, k, v):
        if prefs.__dict__[k] == v:
            print("Reverting to original value:", k, v, prefs.__dict__[k])
            if k in self.prefDiff:
                del self.prefDiff[k]
        else:
            print(k, prefs.__dict__[k], v)
            self.prefDiff[k] = v

