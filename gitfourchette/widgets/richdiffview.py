from gitfourchette.qt import *
from gitfourchette import log
from gitfourchette.widgets.diffmodel import DiffModelError
import html
import pygit2

IMAGE_RESOURCE_TYPE = QTextDocument.ResourceType.ImageResource


class RichDiffView(QTextBrowser):
    def replaceDocument(self, newDocument: QTextDocument):
        if self.document():
            self.document().deleteLater()

        self.setDocument(newDocument)
        self.clearHistory()

        self.setOpenLinks(False)
        self.anchorClicked.connect(self.onAnchorClicked)

    def onAnchorClicked(self, link: QUrl):
        log.info("RichDiffView", F"Anchor clicked: {link}")

    def displayDiffModelError(self, dme: DiffModelError):
        document = QTextDocument()

        pixmap = QApplication.style().standardIcon(dme.icon).pixmap(48, 48)
        document.addResource(IMAGE_RESOURCE_TYPE, QUrl("icon"), pixmap)

        html = (
            "<table width='100%'>"
            "<tr>"
            "<td><img src='icon'/></td>"
            "<td width=8></td>"
            F"<td width='100%'><big>{dme.message}</big><br/>{dme.details}</td>"
            "</tr>"
            "</table>")

        if dme.preformatted:
            html += F"<pre>{html.escape(dme.preformatted)}</pre>"

        html += dme.longform

        document.setHtml(html)
        self.replaceDocument(document)

    def displayImageDiff(self, delta: pygit2.DiffDelta, imageA: QImage, imageB: QImage):
        document = QTextDocument()

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
