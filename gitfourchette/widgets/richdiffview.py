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

        humanSizeA = self.locale().formattedDataSize(delta.old_file.size)
        humanSizeB = self.locale().formattedDataSize(delta.new_file.size)

        textA = self.tr("Old: {0}&times;{1} pixels, {2}").format(imageA.width(), imageA.height(), humanSizeA)
        textB = self.tr("New: {0}&times;{1} pixels, {2}").format(imageB.width(), imageB.height(), humanSizeB)
        newFileDisplayedBelow = self.tr("(new file displayed below)")

        document.setHtml(
            "<style> p { text-align: center; } </style>"
            "<p>"
            F"{textA}<br/>"
            F"{textB}<br/>"
            F"{newFileDisplayedBelow}"
            "</p>"
            "<p><img src='image' /></p>")

        self.replaceDocument(document)
