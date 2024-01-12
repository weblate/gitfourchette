from gitfourchette.diffview.diffdocument import SpecialDiffError
from gitfourchette.porcelain import *
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
        pixmap: QPixmap = icon.pixmap(48, 48)
        document.addResource(IMAGE_RESOURCE_TYPE, QUrl("icon"), pixmap)

        markup = (
            "<table width='100%'>"
            "<tr>"
            f"<td width='{pixmap.width()}px'><img src='icon'/></td>"
            "<td width='100%' style='padding-left: 8px; padding-top: 8px;'>"
            f"<big>{err.message}</big>"
            f"<br/>{err.details}"
            "</td>"
            "</tr>"
            "</table>")

        if err.preformatted:
            markup += F"<pre>{escape(err.preformatted)}</pre>"

        markup += err.longform

        document.setHtml(markup)
        self.replaceDocument(document)

    def displayImageDiff(self, delta: DiffDelta, imageA: QImage, imageB: QImage):
        document = QTextDocument(self)
        document.setObjectName("ImageDiffDocument")

        humanSizeA = self.locale().formattedDataSize(delta.old_file.size)
        humanSizeB = self.locale().formattedDataSize(delta.new_file.size)

        textA = self.tr("Old:") + " " + self.tr("{0}&times;{1} pixels, {2}").format(imageA.width(), imageA.height(), humanSizeA)
        textB = self.tr("New:") + " " + self.tr("{0}&times;{1} pixels, {2}").format(imageB.width(), imageB.height(), humanSizeB)

        if delta.old_file.id == NULL_OID:
            header = f"<span class='add'>{textB}</span>"
            image = imageB
        elif delta.new_file.id == NULL_OID:
            header = f"<span class='del'>{textA} " + self.tr("(<b>deleted file</b> displayed below)") + "</span>"
            image = imageA
        else:
            header = f"<span class='del'>{textA}</span><br><span class='add'>{textB} " + self.tr("(<b>new file</b> displayed below)") + "</span>"
            image = imageB

        image.setDevicePixelRatio(self.devicePixelRatio())
        document.addResource(IMAGE_RESOURCE_TYPE, QUrl("image"), image)

        document.setHtml(
            "<style>.add{color: green;} .del{color: red;}</style>"
            f"<p>{header}</p>"
            "<p style='text-align: center'><img src='image' /></p>")

        self.replaceDocument(document)
