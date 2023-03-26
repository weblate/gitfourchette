from gitfourchette.qt import *


class QComboBoxWithPreview(QComboBox):
    dataPicked = Signal(object)

    class ItemDelegate(QStyledItemDelegate):
        def paint(self, painter, option, index):
            super().paint(painter, option, index)
            painter.save()

            pw: QComboBoxWithPreview = self.parent()
            rect = QRect(option.rect)
            rect.setLeft(rect.left() + pw.longestCaptionWidth + 16)

            isSelected = bool(option.state & QStyle.StateFlag.State_Selected)
            if not isSelected:
                painter.setPen(option.palette.color(QPalette.ColorGroup.Normal, QPalette.ColorRole.PlaceholderText))
            else:
                painter.setPen(option.palette.color(QPalette.ColorGroup.Normal, QPalette.ColorRole.HighlightedText))

            preview = index.data(Qt.ItemDataRole.UserRole + 1)

            painter.drawText(rect, Qt.AlignmentFlag.AlignVCenter, preview)
            painter.restore()

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.numPresets = 0
        self.longestCaptionWidth = 0
        self.longestDataWidth = 0
        self.longestPreviewWidth = 0
        delegate = QComboBoxWithPreview.ItemDelegate(self)
        self.setItemDelegate(delegate)
        self.activated.connect(self.onActivated)

    def addItemWithPreview(self, caption: str, data: object, preview: str):
        i = self.count()
        self.addItem(caption)
        self.setItemData(i, data, Qt.ItemDataRole.UserRole + 0)
        self.setItemData(i, preview, Qt.ItemDataRole.UserRole + 1)
        self.longestCaptionWidth = max(self.longestCaptionWidth, self.fontMetrics().horizontalAdvance(caption))
        self.longestDataWidth    = max(self.longestDataWidth,    self.fontMetrics().horizontalAdvance(str(data)))
        self.longestPreviewWidth = max(self.longestPreviewWidth, self.fontMetrics().horizontalAdvance(preview))
        # if self.isEditable():
        #     self.setMinimumWidth(self.longestDataWidth + 32)
        self.numPresets += 1

    def showPopup(self):
        self.view().setMinimumWidth(self.longestCaptionWidth + self.longestPreviewWidth + 16)
        super().showPopup()

    def onActivated(self, index: int):
        # The signal may be sent for an index beyond the number of presets
        # when the user hits enter with a custom item.
        if index < 0 or index >= self.numPresets:
            return

        data = self.itemData(index, Qt.ItemDataRole.UserRole + 0)
        self.dataPicked.emit(data)

        if self.isEditable():
            self.setEditText(str(data))
