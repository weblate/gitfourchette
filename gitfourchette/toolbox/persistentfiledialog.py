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
    def install(qfd: QFileDialog, key: str):
        savedPath = PersistentFileDialog.getPath(key)
        if savedPath:
            savedPath = os.path.dirname(savedPath)
            if os.path.exists(savedPath):
                qfd.setDirectory(savedPath)
        qfd.fileSelected.connect(lambda path: PersistentFileDialog.savePath(key, path))
        return qfd

    @staticmethod
    def saveFile(parent: QWidget, key: str, caption: str, initialFilename="", filter="", selectedFilter="", deleteOnClose=True):
        qfd = QFileDialog(parent, caption, initialFilename, filter)
        qfd.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        qfd.setFileMode(QFileDialog.FileMode.AnyFile)
        if selectedFilter:
            qfd.selectNameFilter(selectedFilter)
        qfd.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, deleteOnClose)
        qfd.setWindowModality(Qt.WindowModality.WindowModal)
        PersistentFileDialog.install(qfd, key)
        return qfd

    @staticmethod
    def openFile(parent: QWidget, key: str, caption: str, fallbackPath="", filter="", selectedFilter="", deleteOnClose=True):
        qfd = QFileDialog(parent, caption, fallbackPath, filter)
        qfd.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
        qfd.setFileMode(QFileDialog.FileMode.AnyFile)
        if selectedFilter:
            qfd.selectNameFilter(selectedFilter)
        qfd.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, deleteOnClose)
        qfd.setWindowModality(Qt.WindowModality.WindowModal)
        PersistentFileDialog.install(qfd, key)
        return qfd

    @staticmethod
    def openDirectory(parent: QWidget, key: str, caption: str, options=QFileDialog.Option.ShowDirsOnly, deleteOnClose=True):
        qfd = QFileDialog(parent, caption)
        qfd.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
        qfd.setFileMode(QFileDialog.FileMode.Directory)
        qfd.setOptions(options)
        qfd.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, deleteOnClose)
        qfd.setWindowModality(Qt.WindowModality.WindowModal)
        PersistentFileDialog.install(qfd, key)
        return qfd

    @staticmethod
    def saveDirectory(parent: QWidget, key: str, caption: str, options=QFileDialog.Option.ShowDirsOnly, deleteOnClose=True):
        qfd = QFileDialog(parent, caption)
        qfd.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        qfd.setFileMode(QFileDialog.FileMode.Directory)
        qfd.setOptions(options)
        qfd.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, deleteOnClose)
        qfd.setWindowModality(Qt.WindowModality.WindowModal)
        PersistentFileDialog.install(qfd, key)
        return qfd
