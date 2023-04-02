from gitfourchette.qt import *


class PersistentFileDialog:
    @staticmethod
    def getPath(key: str, fallbackPath: str = ""):
        from gitfourchette import settings
        return settings.history.fileDialogPaths.get(key, fallbackPath)

    @staticmethod
    def savePath(key, path):
        if path:
            from gitfourchette import settings
            settings.history.fileDialogPaths[key] = path
            settings.history.write()

    @staticmethod
    def saveFile(parent: QWidget, key: str, caption: str, initialFilename="", filter="", selectedFilter="", deleteOnClose=True):
        previousSavePath = PersistentFileDialog.getPath(key)
        if not previousSavePath:
            initialPath = initialFilename
        else:
            previousSaveDir = os.path.dirname(previousSavePath)
            initialPath = os.path.join(previousSaveDir, initialFilename)

        qfd = QFileDialog(parent, caption, initialPath, filter)
        qfd.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        qfd.setFileMode(QFileDialog.FileMode.AnyFile)
        if selectedFilter:
            qfd.selectNameFilter(selectedFilter)

        qfd.fileSelected.connect(lambda path: PersistentFileDialog.savePath(key, path))

        if deleteOnClose:
            qfd.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        qfd.setWindowModality(Qt.WindowModality.WindowModal)
        return qfd

    @staticmethod
    def openFile(parent: QWidget, key: str, caption: str, filter="", selectedFilter="", fallbackPath="", deleteOnClose=True):
        initialDir = PersistentFileDialog.getPath(key, fallbackPath)

        qfd = QFileDialog(parent, caption, initialDir, filter)
        qfd.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
        qfd.setFileMode(QFileDialog.FileMode.AnyFile)
        if selectedFilter:
            qfd.selectNameFilter(selectedFilter)

        qfd.fileSelected.connect(lambda path: PersistentFileDialog.savePath(key, path))

        if deleteOnClose:
            qfd.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        qfd.setWindowModality(Qt.WindowModality.WindowModal)
        return qfd

    @staticmethod
    def openDirectory(parent: QWidget, key: str, caption: str, options=QFileDialog.Option.ShowDirsOnly, deleteOnClose=True):
        initialDir = PersistentFileDialog.getPath(key)

        qfd = QFileDialog(parent, caption, initialDir)
        qfd.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
        qfd.setFileMode(QFileDialog.FileMode.Directory)
        qfd.setOptions(options)

        qfd.fileSelected.connect(lambda path: PersistentFileDialog.savePath(key, path))

        if deleteOnClose:
            qfd.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        qfd.setWindowModality(Qt.WindowModality.WindowModal)
        return qfd
