import pygit2

from gitfourchette.diffview.diffdocument import SpecialDiffError
from gitfourchette.qt import *
from gitfourchette.toolbox import stockIcon, escape

IMAGE_RESOURCE_TYPE = QTextDocument.ResourceType.ImageResource


class SpecialDiffView(QTextBrowser):
    def replaceDocument(self, newDocument: QTextDocument):
        if self.document():
            self.document().deleteLater()

        self.setDocument(newDocument)
        self.clearHistory()

        self.setOpenLinks(False)

    def displaySpecialDiffError(self, err: SpecialDiffError):
        document = QTextDocument(self)
        document.setObjectName("DiffErrorDocument")

        icon = stockIcon(err.icon)
        pixmap = icon.pixmap(48, 48)
        document.addResource(IMAGE_RESOURCE_TYPE, QUrl("icon"), pixmap)

        markup = (
            "<table width='100%'>"
            "<tr>"
            "<td><img src='icon'/></td>"
            "<td width=8></td>"
            F"<td width='100%'><big>{err.message}</big><br/>{err.details}</td>"
            "</tr>"
            "</table>")

        if err.preformatted:
            markup += F"<pre>{escape(err.preformatted)}</pre>"

        markup += err.longform

        document.setHtml(markup)
        self.replaceDocument(document)

    def displayImageDiff(self, delta: pygit2.DiffDelta, imageA: QImage, imageB: QImage):
        document = QTextDocument(self)
        document.setObjectName("ImageDiffDocument")

        imageB.setDevicePixelRatio(self.devicePixelRatio())

        document.addResource(IMAGE_RESOURCE_TYPE, QUrl("image"), imageB)

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
