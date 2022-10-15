from gitfourchette.qt import *
from gitfourchette.widgets.diffmodel import DiffModelError
import html
import pygit2


class RichDiffView(QTextBrowser):
    def replaceDocument(self, newDocument: QTextDocument):
        if self.document():
            self.document().deleteLater()

        self.setDocument(newDocument)
        self.clearHistory()

    def displayDiffModelError(self, dme: DiffModelError):
        document = QTextDocument()

        pixmap = QApplication.style().standardIcon(dme.icon).pixmap(48, 48)
        document.addResource(QTextDocument.ResourceType.ImageResource, QUrl("icon"), pixmap)

        document.setHtml(
            "<table width='100%'>"
            "<tr>"
            "<td><img src='icon'/></td>"
            "<td width=8></td>"
            F"<td width='100%'><big>{dme.message}</big><br/>{dme.details}</td>"
            "</tr>"
            "</table>"
            F"<pre>{html.escape(dme.preformatted)}</pre>")

        self.replaceDocument(document)

    def displayImageDiff(self, delta: pygit2.DiffDelta, imageA: QImage, imageB: QImage):
        document = QTextDocument()

        imageB.setDevicePixelRatio(self.devicePixelRatio())

        document.addResource(QTextDocument.ResourceType.ImageResource, QUrl("image"), imageB)
        
        humanSizeA = QLocale.system().formattedDataSize(delta.old_file.size)
        humanSizeB = QLocale.system().formattedDataSize(delta.new_file.size)

        document.setHtml(
            "<style> p { text-align: center; } </style>"
            "<p>"
            F"Old: {imageA.width()}&times;{imageA.height()} pixels, {humanSizeA}<br/>"
            F"New: {imageB.width()}&times;{imageB.height()} pixels, {humanSizeB}<br/>"
            F"(new file displayed below)"
            "</p>"
            "<p><img src='image' /></p>")

        self.replaceDocument(document)
